"""Step 3.3: SHAP explanations, readable reasons, the age audit and the truth's Shapley values."""

import numpy as np
import pandas as pd
import pytest

from app.workforce.data import FEATURES
from app.workforce.explain import (
    FEATURE_INFO,
    explain_carer,
    fit_final_model,
    global_importance,
    group_audit,
    make_explainer,
    shap_values,
)
from app.workforce.models import xy
from scripts.explain_attrition import true_shapley
from scripts.generate_workforce import (
    GROUND_TRUTH,
    NULL_FEATURES,
    TERM_FEATURES,
    logit_observed,
)


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_csv("data/workforce/train.csv"), pd.read_csv("data/workforce/test.csv")


@pytest.fixture(scope="module")
def fitted(data):
    train, test = data
    model = fit_final_model(train)
    return model, shap_values(make_explainer(model), test)


def test_shap_values_add_up_to_the_model_output(data, fitted) -> None:
    """Guards ADR-022: base value + sum of SHAP = model log-odds, for every carer."""
    _, test = data
    model, sv = fitted
    raw = model.decision_function(xy(test)[0])
    assert np.allclose(sv.values.sum(axis=1) + sv.base_values, raw, atol=1e-9)


def test_unused_features_get_zero_attribution(fitted) -> None:
    _, sv = fitted
    imp = global_importance(sv)
    assert imp.index[0] in {"tenure_months", "gap_min_per_shift", "short_notice_changes_per_month"}
    assert imp[["late_shift", "shifts_per_week"]].max() == 0  # never split on


def test_explain_carer_orders_reasons_and_offers_support_only_for_raised_risk(data, fitted):
    _, test = data
    model, sv = fitted
    i = 3
    expl = explain_carer(sv, i, test.iloc[i], top=12)
    sizes = [abs(r.log_odds) for r in expl.reasons]
    assert sizes == sorted(sizes, reverse=True)
    assert all((r.support is None) == (r.direction == "lowers") for r in expl.reasons)
    p = model.predict_proba(xy(test.iloc[[i]])[0])[0, 1]
    assert expl.risk == pytest.approx(p, abs=1e-3)


def test_every_feature_has_readable_info() -> None:
    assert set(FEATURE_INFO) == set(FEATURES)


def test_group_audit_selection_rates() -> None:
    groups = pd.Series(["a"] * 5 + ["b"] * 5)
    y = np.array([1, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    p = np.array([0.9, 0.8, 0.7, 0.2, 0.1, 0.6, 0.3, 0.2, 0.1, 0.1])
    audit = group_audit(groups, y, p, top_share=0.4)  # top 4: three from a, one from b
    assert audit.loc["a", "selection_rate"] == pytest.approx(0.6)
    assert audit.loc["b", "selection_rate"] == pytest.approx(0.2)
    assert audit.loc["b", "ratio_to_max"] == pytest.approx(1 / 3)
    assert audit.loc["a", "observed"] == pytest.approx(0.4)


def test_term_features_match_ground_truth(data) -> None:
    """Each term reads only the features it declares (needed for exact true Shapley)."""
    assert set(TERM_FEATURES) == set(GROUND_TRUTH)
    row = {**data[0].iloc[0].to_dict(), "zero_hours": True, "short_notice_changes_per_month": 5}
    for name, term in GROUND_TRUTH.items():
        for f in set(FEATURES) - set(TERM_FEATURES[name]):
            assert term({**row, f: 3}) == term(row), (name, f)


def test_true_shapley_is_efficient_and_zero_for_null_features(data) -> None:
    """Efficiency: per carer, the values sum to truth(x) minus its background mean."""
    train, test = data
    rows, bg = test.head(40), train.head(60)
    phi = true_shapley(rows, bg)
    truth = np.array([logit_observed(r) for r in rows.to_dict("records")])
    bg_mean = np.mean([logit_observed(r) for r in bg.to_dict("records")])
    assert np.allclose(phi.sum(axis=1), truth - bg_mean)
    assert (phi[list(NULL_FEATURES)] == 0).all().all()
