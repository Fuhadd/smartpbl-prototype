from dataclasses import replace

import pytest

from app.matching.bounds import travel_free_continuity_bound
from app.matching.check import check_solution
from app.matching.continuity import Familiarity, continuity_stats, familiarity, penalty_s
from app.matching.data import Client, Scenario
from app.matching.solver import SolverParams, solve
from scripts.sweep_continuity import Point, dominates, pareto
from tests.test_solver import FAR, NEAR, OFFICE, carer, instance, visit

FAST = SolverParams(time_limit_s=1.0)


def fam_client(preferred=(), recent=()) -> Client:
    return Client(
        client_ref="CL-0001",
        location=NEAR,
        needs=frozenset(),
        preferred_carers=tuple(preferred),
        recent_carers=tuple(recent),
    )


def test_familiarity_levels_and_penalties() -> None:
    c = fam_client(preferred=["CR-0001"], recent=["CR-0001", "CR-0002"])
    assert familiarity(c, "CR-0001") is Familiarity.PREFERRED
    assert familiarity(c, "CR-0002") is Familiarity.RECENT
    assert familiarity(c, "CR-0003") is Familiarity.NEW
    assert [penalty_s(c, r, 600) for r in ("CR-0001", "CR-0002", "CR-0003")] == [0, 300, 600]


def two_carer_case() -> tuple[Scenario, object]:
    """CR-0001 starts next to the client but is a stranger; CR-0002 starts 4.7 km away but
    is the client's preferred carer."""
    near = carer("CR-0001").model_copy(update={"start": NEAR, "home": NEAR})
    far = carer("CR-0002").model_copy(update={"start": FAR, "home": FAR})
    client = Client(
        client_ref="CL-0001",
        location=OFFICE,
        needs=frozenset(),
        preferred_carers=("CR-0002",),
        recent_carers=("CR-0002",),
    )
    s, m = instance([near, far], [client], [visit("V-0001", "CL-0001", 480, 540)])
    return s, m


def carer_for(sol, visit_id: str) -> str:
    return next(r.carer_ref for r in sol.routes for st in r.stops if st.visit_id == visit_id)


def test_weight_switches_assignment_to_familiar_carer() -> None:
    s, m = two_carer_case()
    assert carer_for(solve(s, m, FAST), "V-0001") == "CR-0001"  # nearest wins at w=0
    gap = m.seconds(FAR, OFFICE) - m.seconds(NEAR, OFFICE)  # extra driving for CR-0002
    small = solve(s, m, replace(FAST, continuity_weight_s=gap - 60))
    large = solve(s, m, replace(FAST, continuity_weight_s=gap + 60))
    assert carer_for(small, "V-0001") == "CR-0001"  # not worth the detour
    assert carer_for(large, "V-0001") == "CR-0002"  # now it is
    assert check_solution(s, m, large) == []
    stats = continuity_stats(s, large)
    assert (stats.preferred, stats.new, stats.familiar_pct) == (1, 0, 1.0)


def test_continuity_never_causes_a_drop() -> None:
    s, m = two_carer_case()
    only_stranger = s.model_copy(update={"carers": s.carers[:1]})
    sol = solve(only_stranger, m, replace(FAST, continuity_weight_s=3600))
    assert sol.dropped == ()  # a stranger is better than no visit


def test_weight_too_large_for_drop_penalty_is_rejected() -> None:
    s, m = two_carer_case()
    with pytest.raises(ValueError, match="drop_penalty"):
        solve(s, m, replace(FAST, continuity_weight_s=10_000_000))


def test_distinct_carers_counts_multi_visit_clients_only() -> None:
    s, m = instance(
        [carer("CR-0001"), carer("CR-0002")],
        [fam_client(), Client(client_ref="CL-0002", location=FAR, needs=frozenset())],
        [
            visit("V-0001", "CL-0001", 480, 480, dur=30),
            visit("V-0002", "CL-0001", 600, 600, dur=30),
            visit("V-0003", "CL-0002", 480, 500, dur=30),
        ],
    )
    stats = continuity_stats(s, solve(s, m, FAST))
    assert stats.served == 3
    assert stats.distinct_carers_per_client in {1.0, 2.0}  # only CL-0001 has 2+ visits


def test_continuity_ceiling_on_tiny_instance() -> None:
    s, _ = instance(
        [carer("CR-0001")],
        [fam_client(preferred=["CR-0001"], recent=["CR-0001"])],
        [visit("V-0001", "CL-0001", 480, 480, dur=60), visit("V-0002", "CL-0001", 500, 500)],
    )
    bound = travel_free_continuity_bound(s, time_limit_s=5)
    assert (bound.max_familiar, bound.optimal) == (1, True)  # the two visits overlap


def _pt(w, drive_min, familiar, dropped, n=10) -> Point:
    sol = type("S", (), {"travel_s": drive_min * 60, "dropped": ("x",) * dropped})()
    stats = type("C", (), {"preferred": familiar, "recent": 0})()
    return Point(w, sol, stats, n)  # type: ignore[arg-type]


def test_pareto_front_over_three_objectives() -> None:
    a = _pt(0, 600, 3, 1)
    b = _pt(10, 700, 6, 1)
    worse = _pt(20, 750, 5, 1)  # more driving AND fewer familiar than b
    fewer_drops = _pt(30, 800, 5, 0)  # dominated on two axes but fewer drops: kept
    assert dominates(b, worse) and not dominates(b, fewer_drops)
    assert [p.weight_min for p in pareto([a, b, worse, fewer_drops])] == [0, 10, 30]


def test_warm_start_keeps_coverage_and_never_worsens() -> None:
    s, m = two_carer_case()
    reference = solve(s, m, FAST)
    params = replace(FAST, continuity_weight_s=3600)
    warm = solve(s, m, params, initial=reference)
    assert warm.dropped == () and check_solution(s, m, warm) == []
    assert carer_for(warm, "V-0001") == "CR-0002"  # continuity applied from the warm start
    # Visits missing from the scenario are skipped when reading the start routes.
    smaller = s.model_copy(update={"visits": ()})
    assert solve(smaller, m, params, initial=reference).served == 0
