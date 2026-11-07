"""VRPTW solver tests on tiny hand-built instances (haversine travel) plus a smoke test on
the committed scenario. Each solution is re-verified by the independent checker."""

from dataclasses import replace
from pathlib import Path

import pytest

from app.matching.bounds import travel_free_drop_bound
from app.matching.check import check_solution
from app.matching.data import Carer, Client, Location, Scenario, Skill, Visit
from app.matching.solver import Route, SolverParams, Stop, solve
from app.matching.travel import TravelMatrix, haversine_matrix, scenario_points

FAST = SolverParams(time_limit_s=1.0)
OFFICE = Location(lat=52.478, lon=-1.890)
NEAR = Location(lat=52.480, lon=-1.890)  # ~220 m north
FAR = Location(lat=52.520, lon=-1.890)  # ~4.7 km north


def carer(ref: str, skills: set[Skill] = frozenset(), start: int = 420, end: int = 870) -> Carer:
    return Carer(
        carer_ref=ref,
        skills=frozenset({Skill.PERSONAL_CARE, *skills}),
        shift_start=start,
        shift_end=end,
        home=OFFICE,
        start=OFFICE,
    )


def client(ref: str, where: Location, needs: set[Skill] = frozenset()) -> Client:
    return Client(client_ref=ref, location=where, needs=frozenset({Skill.PERSONAL_CARE, *needs}))


def visit(vid: str, cref: str, ws: int, we: int, dur: int = 30, skills=(), critical=False):
    return Visit(
        visit_id=vid,
        client_ref=cref,
        window_start=ws,
        window_end=we,
        duration=dur,
        required_skills=frozenset({Skill.PERSONAL_CARE, *skills}),
        time_critical=critical,
    )


def instance(carers, clients, visits) -> tuple[Scenario, TravelMatrix]:
    s = Scenario(
        name="t", seed=0, carers=tuple(carers), clients=tuple(clients), visits=tuple(visits)
    )
    return s, haversine_matrix(scenario_points(s.carers, s.clients))


def test_single_route_respects_windows_and_order() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR), client("CL-0002", FAR)],
        [
            visit("V-0002", "CL-0002", 540, 570),  # 09:00-09:30
            visit("V-0001", "CL-0001", 480, 500),  # 08:00-08:20
        ],
    )
    sol = solve(s, m, FAST)
    assert sol.dropped == ()
    assert [st.visit_id for st in sol.routes[0].stops] == ["V-0001", "V-0002"]
    assert check_solution(s, m, sol) == []
    first, second = sol.routes[0].stops
    assert 480 * 60 <= first.start_s <= 500 * 60
    assert second.start_s >= first.end_s + second.travel_s


def test_skills_route_visit_to_qualified_carer_only() -> None:
    s, m = instance(
        [carer("CR-0001"), carer("CR-0002", {Skill.CATHETER_CARE})],
        [client("CL-0001", NEAR, {Skill.CATHETER_CARE})],
        [visit("V-0001", "CL-0001", 480, 540, skills=[Skill.CATHETER_CARE])],
    )
    sol = solve(s, m, FAST)
    by_carer = {r.carer_ref: [st.visit_id for st in r.stops] for r in sol.routes}
    assert by_carer == {"CR-0001": [], "CR-0002": ["V-0001"]}


def test_impossible_visit_is_dropped_not_fatal() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR)],
        [visit("V-0001", "CL-0001", 480, 540), visit("V-0002", "CL-0001", 1200, 1230)],
    )
    sol = solve(s, m, FAST)
    assert sol.dropped == ("V-0002",)  # 20:00, outside the 07:00-14:30 shift
    # A time-limited metaheuristic may stop before certifying a local optimum: still valid.
    assert sol.status in {"SUCCESS", "OPTIMAL", "PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED"}
    assert check_solution(s, m, sol) == []


def test_time_critical_visit_kept_when_only_one_fits() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR), client("CL-0002", FAR)],
        [
            visit("V-0001", "CL-0001", 480, 480, dur=60),  # both must start at 08:00
            visit("V-0002", "CL-0002", 480, 480, dur=60, critical=True),
        ],
    )
    sol = solve(s, m, FAST)
    assert sol.dropped == ("V-0001",)


def test_first_solution_only_mode_stops_early() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR)],
        [visit("V-0001", "CL-0001", 480, 540)],
    )
    sol = solve(s, m, replace(FAST, first_solution_only=True))
    assert sol.served == 1 and check_solution(s, m, sol) == []


def test_checker_catches_doctored_solutions() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR, {Skill.MEDICATION})],
        [visit("V-0001", "CL-0001", 480, 540, skills=[Skill.MEDICATION])],
    )
    good = solve(s, m, FAST)
    assert good.dropped == ("V-0001",)  # carer lacks medication
    stop = Stop("V-0001", "CL-0001", 600 * 60, 630 * 60, m.seconds(OFFICE, NEAR))
    bad = replace(good, routes=(Route("CR-0001", 420 * 60, (stop, stop)),), dropped=("V-0001",))
    problems = check_solution(s, m, bad)
    assert any("lacks ['medication']" in p for p in problems)
    assert any("outside window" in p for p in problems)
    assert any("served more than once" in p for p in problems)
    assert any("both served and dropped" in p for p in problems)
    assert any("before the carer can arrive" in p for p in problems)  # second copy overlaps


def test_travel_free_bound_counts_unavoidable_drops() -> None:
    s, _ = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR), client("CL-0002", FAR)],
        [
            visit("V-0001", "CL-0001", 480, 480, dur=60),
            visit("V-0002", "CL-0002", 490, 490, dur=60),  # overlaps V-0001 on one carer
            visit("V-0003", "CL-0001", 600, 620),
        ],
    )
    bound = travel_free_drop_bound(s, time_limit_s=5)
    assert (bound.min_dropped, bound.optimal) == (1, True)


@pytest.mark.slow
def test_committed_scenario_solves_and_verifies() -> None:
    from scripts.solve_baseline import load

    s, m = load()
    sol = solve(s, m, SolverParams(time_limit_s=2.0))
    assert check_solution(s, m, sol) == []
    assert sol.served + len(sol.dropped) == len(s.visits)
    assert len(sol.dropped) >= travel_free_drop_bound(s).min_dropped
    assert Path("docs/results/tier2_baseline.md").exists()
