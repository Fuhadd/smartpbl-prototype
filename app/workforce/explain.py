"""Explanations and fairness audit for the attrition model (Step 3.3).

Everything here would run unchanged on real data. (The check against the synthetic ground
truth lives in scripts/explain_attrition.py, because only synthetic data has one.)

SHAP (TreeExplainer, log-odds): for one carer, each feature's value is its fair share of
the gap between the model's log-odds for that carer and the average log-odds, averaged
over all orders of adding features (Shapley values). They add up exactly:
base value + sum(SHAP) = the model's log-odds for that carer.

Mode: tree_path_dependent, where the "average" is taken over training rows using the
trees' own leaf counts. The interventional mode (explicit background sample) was tried and
rejected: in shap 0.54.1 its values do not add up for HistGradientBoosting models (error
up to 0.5 log-odds, growing with the number of trees; exact for GradientBoosting). See
ADR-022. SHAP's additivity check stays on, and a test guards it.

Explanations are phrased as working conditions the provider can change, plus a support
action, because the intended use is supportive (model card: docs/model-cards/).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import HistGradientBoostingClassifier

from app.workforce.models import candidates, xy


@dataclass(frozen=True)
class FeatureInfo:
    label: str
    fmt: str  # format for the carer's value
    lever: bool  # something the provider can change about how this carer works
    support: str  # what a coordinator could offer if this raises risk


FEATURE_INFO: dict[str, FeatureInfo] = {
    "tenure_months": FeatureInfo("Time with the provider", "{:.0f} months", False,
                                 "check induction, buddying and early supervision"),
    "zero_hours": FeatureInfo("Zero-hours contract", "{}", True,
                              "discuss a guaranteed-hours contract"),
    "late_shift": FeatureInfo("Mainly late shifts", "{}", True, "review shift pattern"),
    "shifts_per_week": FeatureInfo("Shifts per week", "{:.0f}", True,
                                   "check hours match what the carer wants"),
    "short_notice_changes_per_month": FeatureInfo(
        "Short-notice rota changes", "{:.0f} a month", True,
        "give more rota notice and limit late changes"),
    "skills_count": FeatureInfo("Additional skills", "{:.0f}", False, "discuss training goals"),
    "weekly_paid_hours": FeatureInfo("Paid hours a week", "{:.1f} h", True,
                                     "check hours match what the carer wants"),
    "visits_per_shift": FeatureInfo("Visits per shift", "{:.1f}", True, "review round size"),
    "drive_min_per_shift": FeatureInfo("Driving per shift", "{:.0f} min", True,
                                       "review round geography to cut driving"),
    "gap_min_per_shift": FeatureInfo("Unpaid gaps per shift", "{:.0f} min", True,
                                     "tighten the rota to cut unpaid waiting"),
    "split_shift_share": FeatureInfo("Shifts with a 90+ min gap", "{:.0%}", True,
                                     "offer more continuous shifts"),
    "familiar_share": FeatureInfo("Visits to familiar clients", "{:.0%}", True,
                                  "build a regular round of the same clients"),
}  # fmt: skip


def fit_final_model(train: pd.DataFrame) -> HistGradientBoostingClassifier:
    """Re-tune (inner grid search) and refit HGB on all training carers. Deterministic."""
    X, y = xy(train)
    return candidates()["Gradient boosting (HGB)"].fit(X, y).best_estimator_


def make_explainer(model: HistGradientBoostingClassifier) -> shap.TreeExplainer:
    return shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")


def shap_values(explainer: shap.TreeExplainer, df: pd.DataFrame) -> shap.Explanation:
    X, _ = xy(df)
    return explainer(X)


def global_importance(sv: shap.Explanation) -> pd.Series:
    """Mean |SHAP| per feature: the average size of its push on log-odds."""
    return pd.Series(np.abs(sv.values).mean(axis=0), index=sv.feature_names).sort_values(
        ascending=False
    )


@dataclass(frozen=True)
class Reason:
    feature: str
    label: str
    value: str
    log_odds: float  # SHAP contribution
    points: float  # share of (risk - baseline_risk), in percentage points; see percentage_points
    direction: str  # "raises" / "lowers"
    lever: bool
    support: str | None  # only for levers that raise risk


@dataclass(frozen=True)
class CarerExplanation:
    risk: float  # model probability
    # Probability at the SHAP base value (mean log-odds), where the explanation starts.
    # Not the mean predicted probability: sigmoid(mean log-odds) < mean(sigmoid) here.
    baseline_risk: float
    reasons: tuple[Reason, ...]


def _sigmoid(x: float) -> float:
    return float(1 / (1 + np.exp(-x)))


def format_value(feature: str, v: object) -> str:
    """A carer's raw feature value as people read it ("45 min", "62%", "yes")."""
    if isinstance(v, bool | np.bool_):
        return "yes" if v else "no"
    return FEATURE_INFO[feature].fmt.format(v)


def percentage_points(values: np.ndarray, base: float) -> np.ndarray:
    """Split the probability gap sigmoid(base + sum) - sigmoid(base) across features in
    proportion to their SHAP log-odds, in percentage points.

    SHAP is additive in log-odds, not in probability, so converting each value on its own
    (sigmoid(base + v) - sigmoid(base)) would not add up to the score. Proportional
    rescaling keeps each value's sign and ranking and sums exactly to the gap. When the
    contributions cancel (sum near 0) it falls back to the local slope p(1 - p).
    """
    total = float(values.sum())
    p0, p = _sigmoid(base), _sigmoid(base + total)
    if abs(total) < 1e-9:
        return 100 * p0 * (1 - p0) * values
    return 100 * (p - p0) * values / total


def explain_carer(sv: shap.Explanation, i: int, raw: pd.Series, top: int = 5) -> CarerExplanation:
    """Top contributions for row i of `sv`, with readable values and support actions."""
    values = sv.values[i]
    base = float(np.broadcast_to(sv.base_values, (len(sv.values),))[i])
    order = np.argsort(-np.abs(values), kind="stable")[:top]
    points = percentage_points(values, base)
    reasons = []
    for j in order:
        name = sv.feature_names[j]
        info = FEATURE_INFO[name]
        raises = values[j] > 0
        reasons.append(
            Reason(
                feature=name,
                label=info.label,
                value=format_value(name, raw[name]),
                log_odds=round(float(values[j]), 3),
                points=round(float(points[j]), 2),
                direction="raises" if raises else "lowers",
                lever=info.lever,
                support=info.support if raises else None,
            )
        )
    return CarerExplanation(
        risk=round(_sigmoid(base + values.sum()), 3),
        baseline_risk=round(_sigmoid(base), 3),
        reasons=tuple(reasons),
    )


def group_audit(
    groups: pd.Series, y: np.ndarray, p: np.ndarray, top_share: float = 0.2
) -> pd.DataFrame:
    """Per group: size, observed leaver rate, mean predicted risk, and selection rate if the
    top `top_share` by risk are flagged. `ratio_to_max` < 0.8 fails the "four-fifths"
    heuristic for adverse impact on the less-selected group; > 1 means a group is flagged
    more. Neither is a legal test on its own; both prompt a justification."""
    k = max(1, round(len(p) * top_share))
    flagged = np.zeros(len(p), dtype=bool)
    flagged[np.argsort(-p, kind="stable")[:k]] = True
    df = pd.DataFrame({"group": groups.to_numpy(), "y": y, "p": p, "flagged": flagged})
    out = df.groupby("group").agg(
        n=("y", "size"), observed=("y", "mean"), predicted=("p", "mean"),
        selection_rate=("flagged", "mean"),
    )  # fmt: skip
    out["ratio_to_max"] = out.selection_rate / out.selection_rate.max()
    return out
