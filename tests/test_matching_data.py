from pathlib import Path

import pytest
from pydantic import ValidationError

from app.matching.data import (
    Carer,
    Location,
    Scenario,
    Skill,
    Visit,
    can_serve,
    validate_scenario,
)
from scripts import generate_schedule as gen

HOME = Location(lat=52.48, lon=-1.9)


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return gen.generate(gen.SEED)


def carer(skills: set[Skill], start: int = 420, end: int = 870) -> Carer:
    return Carer(
        carer_ref="CR-0001",
        skills=frozenset(skills | {Skill.PERSONAL_CARE}),
        shift_start=start,
        shift_end=end,
        home=HOME,
        start=HOME,
    )


def visit(skills: set[Skill], ws: int = 480, we: int = 540, dur: int = 30) -> Visit:
    return Visit(
        visit_id="V-0001",
        client_ref="CL-0001",
        window_start=ws,
        window_end=we,
        duration=dur,
        required_skills=frozenset(skills | {Skill.PERSONAL_CARE}),
    )


def test_generator_is_deterministic(scenario) -> None:
    assert gen.generate(gen.SEED) == scenario
    assert gen.generate(gen.SEED + 1) != scenario


def test_committed_scenario_matches_generator(scenario) -> None:
    on_disk = Scenario.model_validate_json(Path(gen.OUT).read_text(encoding="utf-8"))
    assert on_disk == scenario  # regenerate with `python -m scripts.generate_schedule`


def test_generated_scenario_is_valid(scenario) -> None:
    assert validate_scenario(scenario) == []
    assert len(scenario.visits) > 2 * len(scenario.clients)


def test_locations_are_in_bounding_box_and_coarse(scenario) -> None:
    points = [c.location for c in scenario.clients] + [c.home for c in scenario.carers]
    for p in points:
        assert gen.LAT_MIN <= p.lat <= gen.LAT_MAX
        assert gen.LON_MIN <= p.lon <= gen.LON_MAX
        assert round(p.lat, 3) == p.lat and round(p.lon, 3) == p.lon  # ~100 m precision


def test_preferences_are_qualified_for_the_client(scenario) -> None:
    carers = {c.carer_ref: c for c in scenario.carers}
    for client in scenario.clients:
        assert set(client.preferred_carers) <= set(client.recent_carers)
        for ref in client.preferred_carers:
            assert client.needs <= carers[ref].skills


def test_visit_skills_and_windows(scenario) -> None:
    for v in scenario.visits:
        client = scenario.client(v.client_ref)
        assert v.required_skills <= client.needs
        width = v.window_end - v.window_start
        assert width == (2 * gen.CRITICAL_HALF if v.time_critical else 2 * gen.WINDOW_HALF)
        if v.time_critical:
            assert Skill.MEDICATION in v.required_skills


def test_every_skill_covered_on_every_shift(scenario) -> None:
    for start, _ in gen.SHIFTS.values():
        on_shift = [c for c in scenario.carers if c.shift_start == start]
        for skill in Skill:
            assert sum(skill in c.skills for c in on_shift) >= gen.MIN_PER_SHIFT_SKILL


@pytest.mark.parametrize(
    ("c", "v", "expected"),
    [
        (carer(set()), visit(set()), True),
        (carer(set()), visit({Skill.MEDICATION}), False),  # missing skill
        (carer({Skill.MEDICATION}), visit({Skill.MEDICATION}), True),
        (carer(set(), 420, 870), visit(set(), 900, 960), False),  # window after shift
        (carer(set(), 420, 870), visit(set(), 830, 900, 45), False),  # can't finish in shift
        (carer(set(), 420, 870), visit(set(), 800, 900, 45), True),  # starts at 13:45 latest
    ],
)
def test_can_serve(c, v, expected) -> None:
    assert can_serve(c, v) is expected


def test_validator_reports_unservable_and_unknown_refs(scenario) -> None:
    impossible = visit({Skill.CATHETER_CARE}, ws=120, we=150)  # 02:00, nobody on shift
    impossible = impossible.model_copy(update={"client_ref": scenario.clients[0].client_ref})
    bad_client = scenario.clients[1].model_copy(update={"preferred_carers": ("CR-9999",)})
    broken = scenario.model_copy(
        update={
            "visits": (*scenario.visits, impossible),
            "clients": (scenario.clients[0], bad_client, *scenario.clients[2:]),
        }
    )
    problems = validate_scenario(broken)
    assert any("V-0001: no carer" in p for p in problems)
    assert any("CR-9999" in p for p in problems)
    assert any("duplicate visit V-0001" in p for p in problems)


def test_model_rejects_impossible_values() -> None:
    with pytest.raises(ValidationError, match="shift_end"):
        carer(set(), 900, 800)
    with pytest.raises(ValidationError, match="personal_care"):
        Carer(
            carer_ref="CR-0002",
            skills=frozenset({Skill.MEDICATION}),
            shift_start=420,
            shift_end=870,
            home=HOME,
            start=HOME,
        )
    with pytest.raises(ValidationError, match="window_end"):
        visit(set(), ws=600, we=500)
    with pytest.raises(ValidationError):
        Carer.model_validate({**carer(set()).model_dump(), "carer_ref": "Jane Doe"})
