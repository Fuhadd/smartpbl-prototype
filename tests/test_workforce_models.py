"""Step 3.2: model candidates, nested CV mechanics, and evaluation helpers."""

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.model_selection import GridSearchCV

import app.workforce.models as wm
from app.workforce.data import FEATURES
from app.workforce.models import (
    bootstrap_ci,
    calibration_table,
    candidates,
    cross_validate_nested,
    precision_at_top,
    xy,
)


@pytest.fixture(scope="module")
def train() -> pd.DataFrame:
    return pd.read_csv("data/workforce/train.csv")


EVENTS: list[tuple[str, frozenset[int]]] = []


class _Recorder(ClassifierMixin, BaseEstimator):
    """Logs the row ids (column 0) of every fit and predict call, then predicts 0.3."""

    def __init__(self, k: int = 0) -> None:
        self.k = k

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "_Recorder":
        EVENTS.append(("fit", frozenset(X.iloc[:, 0].astype(int))))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        EVENTS.append(("predict", frozenset(X.iloc[:, 0].astype(int))))
        p = np.full(len(X), 0.3)
        return np.column_stack([1 - p, p])


def test_nested_cv_never_trains_on_the_validation_fold(monkeypatch) -> None:
    """Every fit for an outer fold, including the inner grid search and the refit, uses
    only that fold's training rows; the validation rows are seen only at prediction."""
    X = pd.DataFrame({"row": np.arange(100), "noise": np.random.default_rng(0).normal(size=100)})
    y = np.array([0, 1] * 50)
    monkeypatch.setattr(wm, "OUTER_REPEATS", 1)
    EVENTS.clear()
    model = GridSearchCV(_Recorder(), {"k": [0, 1]}, cv=2, scoring="neg_brier_score")
    rows, oof = cross_validate_nested({"rec": model}, X, y, {"const": np.full(100, 0.3)})

    outer = wm.RepeatedStratifiedKFold(n_splits=5, n_repeats=1, random_state=wm.SEED)
    fits_since_last: list[frozenset[int]] = []
    folds_checked = 0
    validation = [frozenset(va) for _, va in outer.split(X, y)]
    for kind, ids in EVENTS:
        if kind == "fit":
            fits_since_last.append(ids)
        elif ids == validation[folds_checked]:  # the outer prediction for this fold
            assert all(f.isdisjoint(ids) for f in fits_since_last)
            assert len(fits_since_last) == 2 * 2 + 1  # 2 params x 2 inner folds + refit
            fits_since_last, folds_checked = [], folds_checked + 1
    assert folds_checked == 5
    assert len(rows) == 5 * 2  # one model + one reference, per outer fold
    assert not np.isnan(oof["rec"]).any()


def test_candidates_are_tuned_inside_and_use_all_features(train) -> None:
    X, _ = xy(train)
    assert list(X.columns) == list(FEATURES)
    assert "age_band" not in X.columns
    for model in candidates().values():
        assert isinstance(model, GridSearchCV)
        assert model.scoring == "neg_log_loss"


def test_balanced_weights_inflate_predicted_risk(train) -> None:
    """Reweighting classes to 50:50 moves the average prediction towards 0.5, away from
    the 30% base rate, without improving ranking: it buys recall at a threshold, not
    information, and breaks calibration."""
    X, y = xy(train)
    models = candidates()
    plain = models["Logistic regression"].fit(X, y).predict_proba(X)[:, 1]
    balanced = models["Logistic regression, balanced weights"].fit(X, y).predict_proba(X)[:, 1]
    assert plain.mean() == pytest.approx(y.mean(), abs=0.02)
    assert balanced.mean() > 0.45
    # Same ranking information: rank correlation near 1.
    assert pd.Series(plain).corr(pd.Series(balanced), method="spearman") > 0.95


def test_logistic_regression_recovers_planted_directions(train) -> None:
    """Sanity check against the known mechanism: effects with clear direction come out
    with the right sign (sizes are shrunk by regularisation and are not compared)."""
    X, y = xy(train)
    lr = candidates()["Logistic regression"].fit(X, y).best_estimator_
    coef = dict(zip(FEATURES, lr[-1].coef_[0], strict=True))
    assert coef["tenure_months"] < 0
    assert coef["zero_hours"] > 0
    assert coef["short_notice_changes_per_month"] > 0
    assert coef["familiar_share"] < 0


def test_precision_at_top() -> None:
    y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 1])
    p = np.array([0.9, 0.8, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2])
    assert precision_at_top(y, p, 0.2) == 0.5  # top 2: one leaver
    assert precision_at_top(y, p, 0.3) == pytest.approx(2 / 3)


def test_bootstrap_ci_brackets_estimate_and_is_deterministic() -> None:
    rng = np.random.default_rng(1)
    p = rng.random(300)
    y = (rng.random(300) < p).astype(int)
    from sklearn.metrics import roc_auc_score

    lo, hi = bootstrap_ci(y, p, roc_auc_score, n=500)
    assert lo < roc_auc_score(y, p) < hi
    assert (lo, hi) == bootstrap_ci(y, p, roc_auc_score, n=500)


def test_calibration_table_on_perfectly_calibrated_draws() -> None:
    rng = np.random.default_rng(2)
    p = rng.random(20_000)
    y = (rng.random(20_000) < p).astype(int)
    t = calibration_table(y, p)
    assert len(t) == 10
    assert (t.predicted - t.observed).abs().max() < 0.03
