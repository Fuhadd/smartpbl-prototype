"""A proven lower bound on dropped visits: the same scenario with all travel set to zero,
solved exactly with CP-SAT.

Removing travel can only make scheduling easier, so the most visits servable without
travel is an upper bound on what any real schedule can serve. If even that drops visits,
those drops are caused by capacity (shifts, windows, skill mix), not by the routing
solver. The gap between this bound and the routing solution is the cost of travel plus
any heuristic sub-optimality.
"""

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.matching.data import Scenario, can_serve


@dataclass(frozen=True)
class DropBound:
    min_dropped: int  # proven if optimal, else a valid lower bound from the solver's bound
    optimal: bool
    unservable: tuple[str, ...]  # visits dropped in the relaxation's best solution


def travel_free_drop_bound(scenario: Scenario, time_limit_s: float = 30.0) -> DropBound:
    m = cp_model.CpModel()
    served = {}
    per_carer: dict[str, list[cp_model.IntervalVar]] = {c.carer_ref: [] for c in scenario.carers}
    for v in scenario.visits:
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
        y = m.new_bool_var(f"served_{v.visit_id}")
        m.add(sum(options) == y)  # served by exactly one carer, or not at all
        served[v.visit_id] = y
    for intervals in per_carer.values():
        m.add_no_overlap(intervals)  # a carer does one visit at a time
    m.maximize(sum(served.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = 42
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT failed: {solver.status_name(status)}")
    n = len(scenario.visits)
    max_served = int(solver.best_objective_bound)  # valid even if not proven optimal
    return DropBound(
        min_dropped=n - max_served,
        optimal=status == cp_model.OPTIMAL,
        unservable=tuple(v for v, y in served.items() if not solver.value(y)),
    )
