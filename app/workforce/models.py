"""Attrition models and their evaluation (Step 3.2).

Three candidates, each wrapped in an inner grid search so hyperparameters are chosen on
training folds only (nested cross-validation when evaluated by `cross_validate_nested`):
  - logistic regression on standardised features (tuned: C);
  - the same with class_weight="balanced", to show what reweighting does to probabilities;
  - histogram gradient boosting (tuned: depth, learning rate, leaf size).

Metrics: ROC-AUC (ranking), PR-AUC as average precision (AP: ranking among the positive class,
sensitive to imbalance), Brier score (accuracy of the probabilities themselves).
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, RepeatedStratifiedKFold, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.workforce.data import FEATURES, LABEL

SEED = 42
INNER_FOLDS = 3
OUTER_SPLITS, OUTER_REPEATS = 5, 5

Metric = Callable[[np.ndarray, np.ndarray], float]
METRICS: dict[str, Metric] = {
    "roc_auc": roc_auc_score,
    "pr_auc": average_precision_score,
    "brier": brier_score_loss,
}


def xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    return df[list(FEATURES)].astype(float), df[LABEL].to_numpy(dtype=int)


def _tuned(estimator: BaseEstimator, grid: dict[str, list[object]]) -> GridSearchCV:
    inner = StratifiedKFold(n_splits=INNER_FOLDS, shuffle=True, random_state=SEED)
    # Select on log loss: it rewards good probabilities, not just good ranking.
    return GridSearchCV(estimator, grid, cv=inner, scoring="neg_log_loss", n_jobs=1)


def candidates() -> dict[str, GridSearchCV]:
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    lr_balanced = make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")
    )
    hgb = HistGradientBoostingClassifier(max_iter=150, random_state=SEED)
    c_grid = {"logisticregression__C": [0.01, 0.1, 1.0]}
    return {
        "Logistic regression": _tuned(lr, c_grid),
        "Logistic regression, balanced weights": _tuned(lr_balanced, c_grid),
        "Gradient boosting (HGB)": _tuned(
            hgb,
            {
                "max_depth": [2, 3],
                "learning_rate": [0.03, 0.1],
                "min_samples_leaf": [20, 50],
            },
        ),
    }


@dataclass(frozen=True)
class FoldScores:
    model: str
    fold: int
    scores: dict[str, float]
    best_params: dict[str, object]


def score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {name: float(f(y, p)) for name, f in METRICS.items()}


def cross_validate_nested(
    models: dict[str, BaseEstimator],
    X: pd.DataFrame,
    y: np.ndarray,
    reference: dict[str, np.ndarray] | None = None,
) -> tuple[list[FoldScores], dict[str, np.ndarray]]:
    """Outer repeated stratified CV. Each model (a GridSearchCV) re-tunes inside each
    outer training fold, so the outer validation fold is never seen during selection.
    `reference` maps a name to fixed per-row predictions (e.g. the oracle), scored on the
    same validation folds. Also returns out-of-fold predictions from the first repeat
    (one prediction per row), used for calibration plots."""
    outer = RepeatedStratifiedKFold(
        n_splits=OUTER_SPLITS, n_repeats=OUTER_REPEATS, random_state=SEED
    )
    rows: list[FoldScores] = []
    oof = {name: np.full(len(y), np.nan) for name in models}
    for fold, (tr, va) in enumerate(outer.split(X, y)):
        for name, model in models.items():
            fitted = clone(model).fit(X.iloc[tr], y[tr])
            p = fitted.predict_proba(X.iloc[va])[:, 1]
            rows.append(FoldScores(name, fold, score(y[va], p), dict(fitted.best_params_)))
            if fold < OUTER_SPLITS:
                oof[name][va] = p
        for name, p_ref in (reference or {}).items():
            rows.append(FoldScores(name, fold, score(y[va], p_ref[va]), {}))
    return rows, oof


def bootstrap_ci(
    y: np.ndarray, p: np.ndarray, metric: Metric, n: int = 2000, seed: int = SEED
) -> tuple[float, float]:
    """Percentile 95% interval, resampling rows with replacement."""
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue  # a resample with one class has no AUC
        stats.append(metric(y[idx], p[idx]))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def precision_at_top(y: np.ndarray, p: np.ndarray, share: float) -> float:
    """Leaver rate among the highest-risk `share` of carers: of the people a manager
    would contact with a fixed retention budget, how many were actually going to leave."""
    k = max(1, round(len(y) * share))
    top = np.argsort(-p, kind="stable")[:k]
    return float(y[top].mean())


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Quantile bins of predicted risk: mean predicted vs observed leaver rate."""
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df.p, q=bins, labels=False, duplicates="drop")
    return df.groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
