"""Independent solution checker: re-verifies a schedule from the scenario and the travel
matrix, without trusting the solver. Every solver (OR-Tools, greedy) is checked by it."""

from app.matching.data import Scenario, qualified
from app.matching.solver import Solution
from app.matching.travel import TravelMatrix


def check_solution(scenario: Scenario, matrix: TravelMatrix, solution: Solution) -> list[str]:
    problems: list[str] = []
    visits = {v.visit_id: v for v in scenario.visits}
    carers = {c.carer_ref: c for c in scenario.carers}
    seen: list[str] = []
    for route in solution.routes:
        carer = carers[route.carer_ref]
        here, clock = carer.start, route.departs_s
        if clock < carer.shift_start * 60:
            problems.append(f"{route.carer_ref}: departs before shift start")
        for stop in route.stops:
            v = visits[stop.visit_id]
            seen.append(v.visit_id)
            where = scenario.client(v.client_ref).location
            drive = matrix.seconds(here, where)
            tag = f"{route.carer_ref}/{v.visit_id}"
            if not qualified(carer, v):
                missing = sorted(sk.value for sk in v.required_skills - carer.skills)
                problems.append(f"{tag}: carer lacks {missing}")
            if stop.travel_s != drive:
                problems.append(f"{tag}: reported travel {stop.travel_s}s, matrix says {drive}s")
            if stop.start_s < clock + drive:
                problems.append(f"{tag}: starts before the carer can arrive")
            if not v.window_start * 60 <= stop.start_s <= v.window_end * 60:
                problems.append(f"{tag}: start {stop.start_s // 60} min outside window")
            if stop.end_s != stop.start_s + v.duration * 60:
                problems.append(f"{tag}: wrong duration")
            here, clock = where, stop.end_s
        if clock > carer.shift_end * 60:
            problems.append(f"{route.carer_ref}: last visit ends after shift end")
    duplicates = {v for v in seen if seen.count(v) > 1}
    problems += [f"{v}: served more than once" for v in sorted(duplicates)]
    accounted = set(seen) | set(solution.dropped)
    problems += [f"{v}: neither served nor dropped" for v in sorted(set(visits) - accounted)]
    problems += [f"{v}: both served and dropped" for v in sorted(set(seen) & set(solution.dropped))]
    return problems
