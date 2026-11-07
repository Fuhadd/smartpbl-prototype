from app.matching.check import check_solution
from app.matching.data import Skill
from app.matching.greedy import solve_greedy
from app.matching.solver import SolverParams, solve
from tests.test_solver import FAR, NEAR, OFFICE, carer, client, instance, visit


def myopia_case():
    """CR-0001 (near, medication-trained) and CR-0002 (far, no medication). Two 08:00 visits
    at the same client: greedy gives the first to the nearest carer, CR-0001, who then can't
    do the medication visit. Sending CR-0002 to the first visit serves both."""
    near = carer("CR-0001", {Skill.MEDICATION}).model_copy(update={"start": NEAR})
    far = carer("CR-0002").model_copy(update={"start": FAR})
    return instance(
        [near, far],
        [client("CL-0001", OFFICE, {Skill.MEDICATION})],
        [
            visit("V-0001", "CL-0001", 480, 500, dur=60),
            visit("V-0002", "CL-0001", 480, 500, dur=30, skills=[Skill.MEDICATION]),
        ],
    )


def test_greedy_is_myopic_where_ortools_is_not() -> None:
    s, m = myopia_case()
    greedy = solve_greedy(s, m)
    assert greedy.dropped == ("V-0002",)
    assert check_solution(s, m, greedy) == []
    best = solve(s, m, SolverParams(time_limit_s=1.0))
    assert best.dropped == ()


def test_time_critical_first_on_ties() -> None:
    s, m = instance(
        [carer("CR-0001")],
        [client("CL-0001", NEAR), client("CL-0002", NEAR)],
        [
            visit("V-0001", "CL-0001", 480, 480, dur=60),
            visit("V-0002", "CL-0002", 480, 480, dur=60, critical=True),
        ],
    )
    assert solve_greedy(s, m).dropped == ("V-0001",)  # the critical one got the carer


def test_departs_as_late_as_possible() -> None:
    s, m = instance(
        [carer("CR-0001")], [client("CL-0001", FAR)], [visit("V-0001", "CL-0001", 600, 620)]
    )
    route = solve_greedy(s, m).routes[0]
    assert route.departs_s == route.stops[0].start_s - route.stops[0].travel_s
    assert route.stops[0].start_s == 600 * 60  # no waiting: arrives as the window opens


def test_greedy_on_committed_scenario_is_valid_and_deterministic() -> None:
    from scripts.solve_baseline import load

    s, m = load()
    a, b = solve_greedy(s, m), solve_greedy(s, m)
    assert check_solution(s, m, a) == []
    assert (a.routes, a.dropped) == (b.routes, b.dropped)
    assert a.params is None and a.status == "GREEDY"
