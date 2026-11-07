"""Step 3.1: carer-day features from Tier 2 solutions, and the synthetic workforce."""

import numpy as np
import pandas as pd
import pytest

from app.matching.solver import Route, Solution, Stop
from app.workforce.data import FEATURES, LABEL, PROTECTED, CarerRecord
from app.workforce.features import carer_days
from scripts.generate_workforce import (
    DIR,
    GROUND_TRUTH,
    NULL_FEATURES,
    TARGET_RATE,
    generate,
    logit_observed,
    oracle_probability,
    solve_intercept,
    split,
)
from tests.test_solver import NEAR, OFFICE, carer, client, instance, visit

H = 3600


def _solution(routes: list[Route]) -> Solution:
    return Solution(tuple(routes), (), 0, "SUCCESS", 0.0, None, "haversine")


def test_carer_days_gaps_split_and_familiarity() -> None:
    known = client("CL-0001", NEAR).model_copy(update={"preferred_carers": ("CR-0001",)})
    s, _ = instance(
        [carer("CR-0001"), carer("CR-0002")],
        [known, client("CL-0002", OFFICE)],
        [visit("V-0001", "CL-0001", 480, 500), visit("V-0002", "CL-0002", 720, 740)],
    )
    route = Route(
        "CR-0001",
        departs_s=7 * H + 55 * 60,
        stops=(
            Stop("V-0001", "CL-0001", 8 * H, 8 * H + 1800, travel_s=300),  # 08:00-08:30
            Stop("V-0002", "CL-0002", 12 * H, 12 * H + 1800, travel_s=600),  # 10 min drive
        ),
    )
    a, b = carer_days(s, _solution([route, Route("CR-0002", 0, ())]))
    assert (a.visits, a.service_min, a.drive_min) == (2, 60, 15)
    assert a.gap_min == 210 - 10  # 08:30 -> 12:00 minus the drive
    assert a.split_day and a.longest_gap_min == 200
    assert a.familiar_share == 0.5  # preferred at CL-0001, new at CL-0002
    assert a.paid_min == 75
    assert (b.visits, b.gap_min, b.split_day, b.familiar_share) == (0, 0, False, None)


@pytest.fixture(scope="module")
def generated() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate()


def test_committed_files_match_generator(generated) -> None:
    records, oracle = generated
    train, test = split(records)
    for name, df in (("train", train), ("test", test), ("oracle", oracle)):
        committed = pd.read_csv(DIR / f"{name}.csv")
        fresh = pd.read_csv(pd.io.common.StringIO(df.to_csv(index=False)))
        pd.testing.assert_frame_equal(committed, fresh)


def test_records_valid_and_split_stratified(generated) -> None:
    records, _ = generated
    for row in records.to_dict("records"):
        CarerRecord.model_validate(row)
    train, test = split(records)
    assert set(train.carer_ref).isdisjoint(test.carer_ref)
    assert len(test) == 200
    assert abs(train[LABEL].mean() - test[LABEL].mean()) < 0.01
    assert abs(records[LABEL].mean() - TARGET_RATE) < 0.03


def test_protected_attribute_is_not_a_feature() -> None:
    assert not set(PROTECTED) & set(FEATURES)


def test_age_and_null_features_have_no_direct_effect(generated) -> None:
    records, _ = generated
    row = records.iloc[0].to_dict()
    z = logit_observed(row)
    for key, value in [("age_band", "55+"), *((f, 99) for f in NULL_FEATURES)]:
        assert logit_observed({**row, key: value}) == z, key


def test_every_ground_truth_term_uses_a_feature(generated) -> None:
    """Each term reacts to at least one model feature, so the mechanism is learnable.
    Start from a zero-hours carer with many changes so the interaction term is active."""
    records = generated[0]
    row = {**records.iloc[0].to_dict(), "zero_hours": True, "short_notice_changes_per_month": 5}
    for name, term in GROUND_TRUTH.items():
        assert any(
            term({**row, f: v}) != term(row) for f in FEATURES for v in (0, 1, 3, 10, 200)
        ), name


def test_oracle_probability_shrinks_towards_the_middle() -> None:
    """Averaging over an unobserved factor flattens the sigmoid: the best probability
    from observed features is less extreme than sigmoid(z) itself."""
    z = np.array([-3.0, 0.0, 3.0])
    p = oracle_probability(z, 0.0)
    plain = 1 / (1 + np.exp(-z))
    assert p[1] == pytest.approx(0.5)
    assert p[0] > plain[0] and p[2] < plain[2]
    assert np.all(np.diff(p) > 0)


def test_intercept_hits_target_rate() -> None:
    z = np.random.default_rng(0).normal(0, 1, 500)
    b = solve_intercept(z, 0.2)
    assert oracle_probability(z, b).mean() == pytest.approx(0.2, abs=1e-6)
