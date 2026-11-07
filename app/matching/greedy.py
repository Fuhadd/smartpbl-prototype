"""Greedy baseline: nearest available carer (Step 2.5).

What a coordinator might do by hand, and the comparison point for OR-Tools:
  1. take visits in order of window opening (time-critical first on ties);
  2. for each, consider eligible carers (skills + shift) who can still arrive in the
     window and finish before their shift ends, given where they are and when they are free;
  3. assign the one with the shortest drive (earliest arrival breaks ties);
  4. if nobody can make it, drop the visit.
No look-ahead and no undo: a choice that looks good now can block a later visit.
"""

import time
from dataclasses import dataclass

from app.matching.data import Location, Scenario, can_serve
from app.matching.solver import DROP_PENALTY, TIME_CRITICAL_FACTOR, Route, Solution, Stop
from app.matching.travel import TravelMatrix


@dataclass
class _CarerState:
    at: Location
    free_s: int  # when the carer can leave their current location
    stops: list[Stop]


def solve_greedy(scenario: Scenario, matrix: TravelMatrix) -> Solution:
    t0 = time.perf_counter()
    state = {c.carer_ref: _CarerState(c.start, c.shift_start * 60, []) for c in scenario.carers}
    dropped: list[str] = []
    order = sorted(scenario.visits, key=lambda v: (v.window_start, not v.time_critical, v.visit_id))
    for v in order:
        where = scenario.client(v.client_ref).location
        best: tuple[int, int, str] | None = None  # (drive, arrival, carer_ref)
        for c in scenario.carers:
            if not can_serve(c, v):
                continue
            st = state[c.carer_ref]
            drive = matrix.seconds(st.at, where)
            start = max(st.free_s + drive, v.window_start * 60)
            if start > v.window_end * 60 or start + v.duration * 60 > c.shift_end * 60:
                continue
            if best is None or (drive, start) < best[:2]:
                best = (drive, start, c.carer_ref)
        if best is None:
            dropped.append(v.visit_id)
            continue
        drive, start, ref = best
        st = state[ref]
        st.stops.append(Stop(v.visit_id, v.client_ref, start, start + v.duration * 60, drive))
        st.at, st.free_s = where, start + v.duration * 60

    routes = []
    for c in scenario.carers:
        stops = tuple(state[c.carer_ref].stops)
        # Leave as late as possible for the first visit (no pointless early waiting).
        departs = (
            max(c.shift_start * 60, stops[0].start_s - stops[0].travel_s)
            if stops
            else (c.shift_start * 60)
        )
        routes.append(Route(c.carer_ref, departs, stops))
    travel = sum(r.travel_s for r in routes)
    critical = {v.visit_id for v in scenario.visits if v.time_critical}
    penalty = sum(DROP_PENALTY * (TIME_CRITICAL_FACTOR if d in critical else 1) for d in dropped)
    return Solution(
        routes=tuple(routes),
        dropped=tuple(sorted(dropped)),
        objective=travel + penalty,
        status="GREEDY",
        wall_s=time.perf_counter() - t0,
        params=None,  # not an OR-Tools run
        matrix_backend=matrix.backend,
    )
