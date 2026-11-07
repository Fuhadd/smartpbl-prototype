"""Proven bounds from a travel-free relaxation, solved exactly with CP-SAT.

Removing travel can only make scheduling easier, so anything impossible without travel is
impossible with it. Two bounds share one relaxed model (optional visit intervals per
eligible carer; no overlap per carer; start within window and shift):

  - travel_free_drop_bound: the fewest visits that must be dropped (max served);
  - travel_free_continuity_bound: the most visits a familiar (preferred or recent) carer
    could possibly cover, a ceiling for the continuity trade-off curve.
"""

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.matching.continuity import Familiarity, familiarity
from app.matching.data import Scenario, can_serve


@dataclass(frozen=True)
class DropBound:
    min_dropped: int  # proven if optimal, else a valid lower bound from the solver's bound
    optimal: bool
    unservable: tuple[str, ...]  # visits dropped in the relaxation's best solution


@dataclass(frozen=True)
class ContinuityBound:
    max_familiar: int  # most visits that could be served by a familiar carer
    visits: int
    optimal: bool

    @property
    def max_familiar_pct(self) -> float:
        return self.max_familiar / self.visits


@dataclass
class _Relaxed:
    model: cp_model.CpModel
    served: dict[str, cp_model.IntVar]
    familiar: list[cp_model.IntVar]


def _relaxed(scenario: Scenario) -> _Relaxed:
    m = cp_model.CpModel()
    served: dict[str, cp_model.IntVar] = {}
    familiar: list[cp_model.IntVar] = []
    per_carer: dict[str, list[cp_model.IntervalVar]] = {c.carer_ref: [] for c in scenario.carers}
    for v in scenario.visits:
        client = scenario.client(v.client_ref)
        options = []
        for c in scenario.carers:
            if not can_serve(c, v):
                continue
            lo = max(v.window_start, c.shift_start)
            hi = min(v.window_end, c.shift_end - v.duration)
            x = m.new_bool_var(f"x_{v.visit_id}_{c.carer_ref}")
            start = m.new_int_var(lo, hi, f"s_{v.visit_id}_{c.carer_ref}")
            per_carer[c.carer_ref].append(
                m.new_optional_fixed_size_interval_var(start, v.duration, x, f"i_{v.visit_id}")
            )
            options.append(x)
            if familiarity(client, c.carer_ref) is not Familiarity.NEW:
                familiar.append(x)
        y = m.new_bool_var(f"served_{v.visit_id}")
        m.add(sum(options) == y)  # served by exactly one carer, or not at all
        served[v.visit_id] = y
    for intervals in per_carer.values():
        m.add_no_overlap(intervals)  # a carer does one visit at a time
    return _Relaxed(m, served, familiar)


def _solve(model: cp_model.CpModel, time_limit_s: float) -> tuple[cp_model.CpSolver, bool]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT failed: {solver.status_name(status)}")
    return solver, status == cp_model.OPTIMAL


def travel_free_drop_bound(scenario: Scenario, time_limit_s: float = 30.0) -> DropBound:
    r = _relaxed(scenario)
    r.model.maximize(sum(r.served.values()))
    solver, optimal = _solve(r.model, time_limit_s)
    max_served = int(solver.best_objective_bound)  # valid even if not proven optimal
    return DropBound(
        min_dropped=len(scenario.visits) - max_served,
        optimal=optimal,
        unservable=tuple(v for v, y in r.served.items() if not solver.value(y)),
    )


def travel_free_continuity_bound(scenario: Scenario, time_limit_s: float = 30.0) -> ContinuityBound:
    r = _relaxed(scenario)
    r.model.maximize(sum(r.familiar))
    solver, optimal = _solve(r.model, time_limit_s)
    return ContinuityBound(int(solver.best_objective_bound), len(scenario.visits), optimal)
