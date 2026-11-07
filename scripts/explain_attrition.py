"""Step 3.3: SHAP explanations, a check against the synthetic ground truth, and an age audit.

Usage: uv run python -m scripts.explain_attrition
Writes docs/results/tier3_explain.md and docs/figures/tier3_shap_{beeswarm,waterfall,
vs_truth}.png.

The ground-truth check is possible only because the data is synthetic. For each carer, the
*true* Shapley value of each feature is computed from the generator's log-odds function,
with the training carers as the background distribution (the distribution SHAP's
path-dependent mode uses for the model). If the model learned the mechanism, its SHAP values
should track these. Where features are correlated (gaps and split shifts) the two
definitions can legitimately differ, so this is a check, not an identity.
"""

import statistics
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.workforce.data import FEATURES, LABEL
from app.workforce.explain import (
    FEATURE_INFO,
    explain_carer,
    fit_final_model,
    global_importance,
    group_audit,
    make_explainer,
    shap_values,
)
from app.workforce.models import SEED, candidates, xy
from scripts.generate_workforce import GROUND_TRUTH, NULL_FEATURES, TERM_FEATURES

DATA = Path("data/workforce")
RESULTS = Path("docs/results/tier3_explain.md")
FIG = Path("docs/figures")
MODEL_COLOUR, TRUTH_COLOUR = "#eb6834", "#52514e"  # HGB slot as in 3.2; truth in muted ink
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
Row = dict[str, object]


def _term_values(term: Callable[[Row], float], rows: list[Row]) -> np.ndarray:
    return np.array([term(r) for r in rows])


def true_shapley(records: pd.DataFrame, background: pd.DataFrame) -> pd.DataFrame:
    """Interventional Shapley values of the ground-truth log-odds, per carer and feature.

    One-feature term h(x_a): phi_a = h(x) - mean over background of h.
    Two-feature term h(x_a, x_b) (the interaction), with v(S) = mean over background rows z
    of h(x_S, z_rest):  phi_a = 1/2 [v(a) - v(0)] + 1/2 [v(ab) - v(b)], and likewise for b.
    """
    rows: list[Row] = records.to_dict("records")
    bg: list[Row] = background.to_dict("records")
    phi = pd.DataFrame(0.0, index=records.index, columns=list(FEATURES))
    for name, term in GROUND_TRUTH.items():
        feats = TERM_FEATURES[name]
        v_empty = _term_values(term, bg).mean()
        v_all = _term_values(term, rows)
        if len(feats) == 1:
            phi[feats[0]] += v_all - v_empty
            continue
        a, b = feats
        v_a = np.array([np.mean([term({**z, a: r[a]}) for z in bg]) for r in rows])
        v_b = np.array([np.mean([term({**z, b: r[b]}) for z in bg]) for r in rows])
        phi[a] += 0.5 * (v_a - v_empty) + 0.5 * (v_all - v_b)
        phi[b] += 0.5 * (v_b - v_empty) + 0.5 * (v_all - v_a)
    return phi


def _style(ax: plt.Axes, title: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=10)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8)


def chart_vs_truth(model_imp: pd.Series, truth_imp: pd.Series) -> None:
    order = truth_imp.sort_values().index  # most important at the top
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    ax.barh(y + 0.2, truth_imp[order], 0.36, color=TRUTH_COLOUR, label="Ground truth")
    ax.barh(y - 0.2, model_imp[order], 0.36, color=MODEL_COLOUR, label="HGB model (SHAP)")
    labels = [FEATURE_INFO[f].label + (" (no true effect)" if f in NULL_FEATURES else "")
              for f in order]  # fmt: skip
    ax.set_yticks(y, labels)
    ax.set_xlabel("Mean |contribution| to log-odds", color=MUTED, fontsize=8)
    _style(ax, "Feature importance: what the model learned vs the generator")
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "tier3_shap_vs_truth.png", dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def _shap_plot(path: Path, draw: Callable[[], None], title: str) -> None:
    plt.figure(facecolor=SURFACE)
    np.random.seed(SEED)  # shap's beeswarm jitters dots with the global RNG
    draw()
    fig = plt.gcf()
    fig.suptitle(title, x=0.01, ha="left", color=INK, fontsize=11)
    fig.savefig(path, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def _labelled(sv: shap.Explanation) -> shap.Explanation:
    out = sv[:, :]
    out.feature_names = [FEATURE_INFO[f].label for f in sv.feature_names]
    return out


def main() -> None:
    train = pd.read_csv(DATA / "train.csv")
    test = pd.read_csv(DATA / "test.csv")
    records = pd.concat([train, test], ignore_index=True)
    model = fit_final_model(train)
    explainer = make_explainer(model)
    background = train

    # 1. Global explanation over all 1,000 carers, and agreement with the truth.
    sv_all = shap_values(explainer, records)
    model_imp = global_importance(sv_all)
    phi = true_shapley(records, background)
    truth_imp = phi.abs().mean().sort_values(ascending=False)
    shap_df = pd.DataFrame(sv_all.values, columns=list(FEATURES))
    corr = {f: shap_df[f].corr(phi[f]) for f in FEATURES if f not in NULL_FEATURES}
    rank_corr = model_imp.rank().corr(truth_imp.rank(), method="spearman")
    smallest_real = min(model_imp[f] for f in FEATURES if f not in NULL_FEATURES)
    largest_null = max(model_imp[f] for f in NULL_FEATURES)
    chart_vs_truth(model_imp, truth_imp)
    _shap_plot(FIG / "tier3_shap_beeswarm.png",
               lambda: shap.plots.beeswarm(_labelled(sv_all), max_display=12, show=False),
               f"SHAP values for {len(records)} carers (log-odds of leaving)")  # fmt: skip

    # 2. Local explanation: the highest-risk carer in the test split.
    sv_test = shap_values(explainer, test)
    p_test = model.predict_proba(xy(test)[0])[:, 1]
    i = int(np.argmax(p_test))
    carer = test.iloc[i]
    expl = explain_carer(sv_test, i, carer)
    _shap_plot(FIG / "tier3_shap_waterfall.png",
               lambda: shap.plots.waterfall(_labelled(sv_test)[i], max_display=8, show=False),
               f"Why {carer.carer_ref} is flagged (log-odds; risk {expl.risk:.0%})")  # fmt: skip

    # 3. Age audit on 1,000 out-of-sample predictions: out-of-fold for the training carers
    #    (nested: tuned inside each fold), final-model predictions for the test carers.
    X, y = xy(train)
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    hgb = candidates()["Gradient boosting (HGB)"]
    oof = cross_val_predict(hgb, X, y, method="predict_proba", cv=cv)[:, 1]
    p_all = np.concatenate([oof, p_test])
    y_all = records[LABEL].to_numpy(dtype=int)
    oracle = pd.read_csv(DATA / "oracle.csv").set_index("carer_ref").p_oracle
    audit = group_audit(records.age_band, y_all, p_all)
    audit["oracle"] = (
        records.assign(o=oracle.loc[records.carer_ref].to_numpy()).groupby("age_band").o.mean()
    )
    by_band = shap_df.assign(age_band=records.age_band).groupby("age_band").mean()
    carriers = by_band.loc["18-24"] - by_band.loc["55+"]

    out = [
        "# Tier 3 explainability: SHAP, ground-truth check and age audit",
        "",
        "- Model: HGB re-tuned on the 800 training carers ("
        + ", ".join(
            f"{k}={model.get_params()[k]}"
            for k in ("max_depth", "learning_rate", "min_samples_leaf")
        )
        + f"); seed {SEED}.",
        f"- SHAP {shap.__version__}, TreeExplainer, tree_path_dependent (ADR-022); "
        f"truth computed against {len(background)} training carers; log-odds. Base value "
        f"{float(np.ravel(sv_all.base_values)[0]):.3f}.",
        "",
        "## Does SHAP recover the mechanism? (synthetic data only)",
        "",
        f"- Rank correlation of global importance, model vs truth: **{rank_corr:.2f}** "
        "(Spearman, 12 features).",
        f"- Null features: largest mean |SHAP| {largest_null:.3f} vs smallest real effect "
        f"{smallest_real:.3f}.",
        f"- Per-carer agreement (Pearson r between SHAP and true Shapley value, "
        f"{len(records)} carers), median {statistics.median(corr.values()):.2f}:",
        "",
        "| Feature | Mean \\|SHAP\\| (model) | Mean \\|true\\| | Per-carer r |",
        "|---|---|---|---|",
    ]
    for f in truth_imp.index:
        r = "no true effect" if f in NULL_FEATURES else f"{corr[f]:.2f}"
        out.append(f"| {FEATURE_INFO[f].label} | {model_imp[f]:.3f} | {truth_imp[f]:.3f} | {r} |")
    out += [
        "",
        "![SHAP vs truth](../figures/tier3_shap_vs_truth.png)",
        "",
        "![Beeswarm](../figures/tier3_shap_beeswarm.png)",
        "",
        f"## Local explanation: {carer.carer_ref} (highest model risk in the test split)",
        "",
        f"Model risk **{expl.risk:.0%}** vs {expl.baseline_risk:.0%} at the baseline "
        f"(base value). Actually left: {'yes' if carer[LABEL] else 'no'}.",
        "",
        "| Factor | This carer | Effect (log-odds) | Provider can change it? | Support to offer |",
        "|---|---|---|---|---|",
    ]
    for r in expl.reasons:
        out.append(
            f"| {r.label} | {r.value} | {r.log_odds:+.2f} ({r.direction} risk) "
            f"| {'yes' if r.lever else 'no'} | {r.support or '-'} |"
        )
    out += [
        "",
        "![Waterfall](../figures/tier3_shap_waterfall.png)",
        "",
        "## Age audit (age is never a model input)",
        "",
        f"Out-of-sample predictions for all {len(records)} carers (out-of-fold for training, "
        "final model for test). Flagged = top 20% by risk.",
        "",
        "| Age band | Carers | Observed leaver rate | Mean predicted | Mean oracle | Flagged "
        "| Ratio to most-flagged |",
        "|---|---|---|---|---|---|---|",
    ]
    for band, a in audit.iterrows():
        out.append(
            f"| {band} | {int(a.n)} | {a.observed:.1%} | {a.predicted:.1%} | {a.oracle:.1%} "
            f"| {a.selection_rate:.1%} | {a.ratio_to_max:.2f} |"
        )
    out += [
        "",
        "Features carrying the age gap (mean SHAP, 18-24 minus 55+, log-odds):",
        "",
        *(
            f"- {FEATURE_INFO[f].label}: {carriers[f]:+.3f}"
            for f in carriers.abs().sort_values(ascending=False).index[:4]
        ),
        "",
    ]
    RESULTS.write_text("\n".join(out), encoding="utf-8")
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
