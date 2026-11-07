"""Scheduling service: resolve travel times, solve, explain, persist and audit one run.

All solver work happens before any database write (as in the Tier 1 pipeline), so a
10-20 s solve never holds a transaction open. The caller commits.
"""

from pathlib import Path
from uuid import uuid4

import httpx
import ortools
from sqlalchemy.orm import Session

from app.audit.log import input_hash, record
from app.audit.models import EventType, SubjectType
from app.core.config import get_settings
from app.matching.check import check_solution
from app.matching.continuity import continuity_stats
from app.matching.data import Scenario
from app.matching.explain import explain
from app.matching.greedy import solve_greedy
from app.matching.models import ScheduleAssignment, ScheduleRun
from app.matching.solver import SolverParams, solve
from app.matching.travel import (
    OSRMClient,
    TravelMatrix,
    cached_matrix,
    haversine_matrix,
    scenario_points,
)

SOLVER = f"ortools-{ortools.__version__}"


def resolve_matrix(scenario: Scenario) -> TravelMatrix:
    """Cached OSRM matrix for these exact points if one exists; else live OSRM if configured;
    else the calibrated haversine fallback. The chosen backend is recorded on the run."""
    settings = get_settings()
    points = scenario_points(scenario.carers, scenario.clients)
    cache = Path(settings.travel_cache_dir)
    for f in sorted(cache.glob("*.json")):
        m = TravelMatrix.model_validate_json(f.read_text(encoding="utf-8"))
        if m.points == points:
            return m
    if settings.osrm_base_url and settings.osrm_data_version:
        client = OSRMClient(settings.osrm_base_url, data_version=settings.osrm_data_version)
        try:
            return cached_matrix(points, client.backend, client.table, cache)
        except httpx.HTTPError:
            pass  # OSRM down: degrade to the fallback rather than fail the request
    return haversine_matrix(points)


def run_schedule(
    session: Session,
    scenario: Scenario,
    *,
    time_limit_s: float,
    continuity_weight_min: int,
    requested_by: str,
) -> ScheduleRun:
    matrix = resolve_matrix(scenario)
    base = solve(scenario, matrix, SolverParams(time_limit_s=time_limit_s))
    solution = base
    if continuity_weight_min > 0:  # two-phase: continuity can never cost a visit (note 13)
        params = SolverParams(
            time_limit_s=time_limit_s, continuity_weight_s=continuity_weight_min * 60
        )
        solution = solve(scenario, matrix, params, initial=base)
    if problems := check_solution(scenario, matrix, solution):
        raise RuntimeError(f"solver returned an invalid schedule: {problems[:3]}")
    assigned, dropped = explain(scenario, matrix, solution)
    stats = continuity_stats(scenario, solution)
    # The comparison point shown on the overview ("-3.1 h vs greedy baseline"): what a
    # nearest-available-carer rota would do on the same day and matrix (Step 2.5).
    greedy = solve_greedy(scenario, matrix)
    greedy_stats = continuity_stats(scenario, greedy)

    run_params = {
        "time_limit_s": time_limit_s,
        "continuity_weight_min": continuity_weight_min,
        "two_phase": continuity_weight_min > 0,
        "first_solution": solution.params.first_solution if solution.params else None,
        "metaheuristic": solution.params.metaheuristic if solution.params else None,
        "drop_penalty": solution.params.drop_penalty if solution.params else None,
    }
    scenario_json = scenario.model_dump_json()
    run = ScheduleRun(
        id=uuid4(),  # known before insert, so the audit event can reference it
        scenario_name=scenario.name,
        scenario_seed=scenario.seed,
        scenario_hash=input_hash(scenario_json),  # keyed HMAC; the scenario isn't stored
        solver=SOLVER,
        params=run_params,
        status=solution.status,
        objective=solution.objective,
        travel_s=solution.travel_s,
        wall_s=round(base.wall_s + (solution.wall_s if solution is not base else 0), 3),
        matrix_backend=matrix.backend,
        metrics={
            "visits": len(scenario.visits),
            "served": solution.served,
            "dropped": len(solution.dropped),
            "familiar_pct": round(stats.familiar_pct, 4),
            "preferred_pct": round(stats.preferred_pct, 4),
            "distinct_carers_per_client": round(stats.distinct_carers_per_client, 3),
            "carers_used": sum(1 for r in solution.routes if r.stops),
            "baseline": {
                "solver": "greedy",
                "travel_s": greedy.travel_s,
                "served": greedy.served,
                "familiar_pct": round(greedy_stats.familiar_pct, 4),
            },
        },
        dropped=[
            {
                "visit_id": d.visit_id,
                "client_ref": d.client_ref,
                "reason": d.reason.value,
                "eligible_carers": d.eligible_carers,
                "time_critical": d.time_critical,
                "detail": d.detail,
            }
            for d in dropped
        ],
        requested_by=requested_by,
    )
    run.assignments = [
        ScheduleAssignment(
            carer_ref=a.carer_ref,
            sequence=a.sequence,
            visit_id=a.visit_id,
            client_ref=a.client_ref,
            start_s=a.start_s,
            end_s=a.end_s,
            travel_s=a.travel_s,
            familiarity=a.familiarity.value,
            reasons=a.reasons,
        )
        for a in assigned
    ]
    session.add(run)
    record(  # written once and never updated: the audit table is append-only
        session,
        EventType.SCHEDULE_SOLVED,
        actor=f"user:{requested_by}",
        subject=(SubjectType.SCHEDULE_RUN, str(run.id)),
        input_text=scenario_json,  # hashed (HMAC), never stored
        model_name="ortools",
        model_version=ortools.__version__,
        output={
            "run_id": str(run.id),
            "params": run_params,
            "scenario_name": scenario.name,
            "scenario_seed": scenario.seed,
            "objective": solution.objective,
            "status": solution.status,
            "travel_s": solution.travel_s,
            "dropped": len(solution.dropped),
            "matrix_backend": matrix.backend,
        },
    )
    session.flush()
    return run
