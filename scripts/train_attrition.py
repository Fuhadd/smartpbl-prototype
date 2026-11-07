"""Step 3.2: compare attrition models with nested CV, then score once on the test split.

Usage: uv run python -m scripts.train_attrition
Reads data/workforce/{train,test,oracle}.csv. Writes docs/results/tier3_models.md and
docs/figures/tier3_{roc_pr,calibration}.png.

Protocol (ADR-021): 5x5 repeated stratified CV on the 800 training carers is the main
estimate; inside each outer training fold a 3-fold grid search picks hyperparameters.
The oracle (best possible probabilities) and a constant base-rate predictor are scored on
the same folds. The test split (200 carers, 60 leavers) is used once, at the end, and
reported next to the oracle on the same rows because the split is unusually easy.
"""

import statistics
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve

from app.workforce.models import (
    METRICS,
    OUTER_REPEATS,
    OUTER_SPLITS,
    SEED,
    FoldScores,
    bootstrap_ci,
    calibration_table,
    candidates,
    cross_validate_nested,
    precision_at_top,
    score,
    xy,
)

DATA = Path("data/workforce")
RESULTS = Path("docs/results/tier3_models.md")
FIG_CURVES = Path("docs/figures/tier3_roc_pr.png")
FIG_CALIBRATION = Path("docs/figures/tier3_calibration.png")
ORACLE, BASE_RATE = "Oracle (true P given features)", "Base rate (constant)"
LR, LR_BAL, HGB = (
    "Logistic regression",
    "Logistic regression, balanced weights",
    "Gradient boosting (HGB)",
)
COLOURS = {LR: "#2a78d6", HGB: "#eb6834", LR_BAL: "#1baf7a"}  # validated slots 1-3
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
LABELS = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC (AP)", "brier": "Brier"}


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    train = pd.read_csv(DATA / "train.csv")
    test = pd.read_csv(DATA / "test.csv")
    oracle = pd.read_csv(DATA / "oracle.csv").set_index("carer_ref").p_oracle
    return train, test, oracle


def _style(ax: plt.Axes, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=10)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=8)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=8)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8)


def chart_curves(y: np.ndarray, oof: dict[str, np.ndarray], p_oracle: np.ndarray) -> None:
    fig, (roc_ax, pr_ax) = plt.subplots(1, 2, figsize=(10, 4.4), facecolor=SURFACE)
    series = [(LR, oof[LR]), (HGB, oof[HGB]), (ORACLE, p_oracle)]
    for name, p in series:
        style = {"color": INK, "ls": "--", "lw": 1.5} if name == ORACLE else {
            "color": COLOURS[name], "lw": 2}  # fmt: skip
        fpr, tpr, _ = roc_curve(y, p)
        roc_ax.plot(fpr, tpr, label=name, **style)
        prec, rec, _ = precision_recall_curve(y, p)
        pr_ax.plot(rec, prec, label=name, **style)
    roc_ax.plot([0, 1], [0, 1], color=MUTED, lw=0.8, ls=":")
    pr_ax.axhline(y.mean(), color=MUTED, lw=0.8, ls=":")
    pr_ax.annotate(f"base rate {y.mean():.0%}", (0.02, y.mean() - 0.05), ha="left",
                   color=MUTED, fontsize=8)  # fmt: skip
    _style(roc_ax, "ROC curve", "False positive rate", "True positive rate (recall)")
    _style(pr_ax, "Precision-recall curve", "Recall", "Precision")
    pr_ax.set_ylim(0, 1.02)
    handles, labels = roc_ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, labelcolor=INK, fontsize=9, ncol=3,
               loc="upper left", bbox_to_anchor=(0.01, 0.93))  # fmt: skip
    fig.suptitle(f"Out-of-fold predictions, {len(y)} training carers (seed {SEED})",
                 x=0.01, ha="left", color=INK, fontsize=11)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(FIG_CURVES, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def chart_calibration(y: np.ndarray, oof: dict[str, np.ndarray], p_oracle: np.ndarray) -> None:
    fig, (rel_ax, tru_ax) = plt.subplots(1, 2, figsize=(10, 4.4), facecolor=SURFACE)
    for name in (LR, LR_BAL, HGB):
        t = calibration_table(y, oof[name])
        rel_ax.plot(t.predicted, t.observed, marker="o", ms=5, lw=2, color=COLOURS[name],
                    label=name)  # fmt: skip
        tru_ax.scatter(p_oracle, oof[name], s=9, alpha=0.45, color=COLOURS[name],
                       edgecolors="none")  # fmt: skip
    for ax in (rel_ax, tru_ax):
        ax.plot([0, 1], [0, 1], color=INK, lw=1.2, ls="--")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
    _style(rel_ax, "Reliability (10 quantile bins)", "Mean predicted risk", "Observed leaver rate")
    _style(tru_ax, "Predicted vs true probability", "Oracle probability", "Model probability")
    handles, labels = rel_ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, labelcolor=INK, fontsize=9, ncol=3,
               loc="upper left", bbox_to_anchor=(0.01, 0.93))  # fmt: skip
    fig.suptitle("Calibration: out-of-fold predictions on the training carers", x=0.01,
                 ha="left", color=INK, fontsize=11)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(FIG_CALIBRATION, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def cv_table(rows: list[FoldScores], names: list[str]) -> list[str]:
    out = ["| Model | ROC-AUC | PR-AUC (AP) | Brier (lower is better) |", "|---|---|---|---|"]
    for name in names:
        cells = []
        for m in METRICS:
            vals = [r.scores[m] for r in rows if r.model == name]
            cells.append(f"{statistics.mean(vals):.3f} ± {statistics.stdev(vals):.3f}")
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    return out


def paired(rows: list[FoldScores], a: str, b: str, metric: str) -> tuple[float, int, int]:
    """Mean per-fold difference a - b, and in how many folds a was better."""
    by = {(r.model, r.fold): r.scores[metric] for r in rows}
    folds = sorted({r.fold for r in rows})
    diffs = [by[(a, f)] - by[(b, f)] for f in folds]
    better = sum((d < 0) if metric == "brier" else (d > 0) for d in diffs)
    return statistics.mean(diffs), better, len(folds)


def main() -> None:
    train, test, oracle = load()
    X, y = xy(train)
    Xt, yt = xy(test)
    p_or_train = oracle.loc[train.carer_ref].to_numpy()
    p_or_test = oracle.loc[test.carer_ref].to_numpy()
    models = candidates()
    reference = {ORACLE: p_or_train, BASE_RATE: np.full(len(y), y.mean())}
    rows, oof = cross_validate_nested(models, X, y, reference)

    names = [*models, ORACLE, BASE_RATE]
    n_folds = OUTER_SPLITS * OUTER_REPEATS
    out = [
        "# Tier 3 models: attrition prediction",
        "",
        f"- Data: {len(train)} training carers ({y.sum()} leavers, {y.mean():.1%}); "
        f"test {len(test)} ({yt.sum()} leavers). Seed {SEED}. Synthetic: see "
        "`data/workforce/DATA_CARD.md`.",
        f"- Main estimate: nested CV, {OUTER_SPLITS}-fold x {OUTER_REPEATS} repeats "
        f"stratified ({n_folds} outer folds of {len(y) // OUTER_SPLITS}); hyperparameters "
        "chosen by a 3-fold inner grid search on log loss, inside each outer training fold.",
        "- Mean ± SD over outer folds. Folds overlap, so the SD shows spread, "
        "not a standard error of the mean.",
        "",
        "## Cross-validation (training carers)",
        "",
        *cv_table(rows, names),
        "",
        "## Paired comparison over the same folds",
        "",
        "| Comparison | Metric | Mean difference | Folds where first is better |",
        "|---|---|---|---|",
    ]
    for a, b in ((HGB, LR), (LR_BAL, LR), (ORACLE, LR), (ORACLE, HGB)):
        for m in METRICS:
            d, better, n = paired(rows, a, b, m)
            out.append(f"| {a} vs {b} | {LABELS[m]} | {d:+.3f} | {better}/{n} |")
    out += ["", "## Hyperparameters chosen in the outer folds", ""]
    for name in models:
        counts = Counter(str(r.best_params) for r in rows if r.model == name)
        top = ", ".join(f"`{p}` x{n}" for p, n in counts.most_common(3))
        out.append(f"- **{name}:** {top}")

    out += [
        "",
        "## Test split (used once)",
        "",
        "Each model is re-tuned and fitted on all 800 training carers. 95% bootstrap "
        "intervals (2,000 resamples). *Error vs truth* is the mean |model - oracle| "
        "probability, only measurable because the data is synthetic.",
        "",
        "| Model | ROC-AUC | PR-AUC (AP) | Brier | Error vs truth |",
        "|---|---|---|---|---|",
    ]
    test_preds = {name: m.fit(X, y).predict_proba(Xt)[:, 1] for name, m in models.items()}
    test_preds[ORACLE] = p_or_test
    for name, p in test_preds.items():
        cells = []
        for m, f in METRICS.items():
            lo, hi = bootstrap_ci(yt, p, f)
            cells.append(f"{score(yt, p)[m]:.3f} ({lo:.3f} to {hi:.3f})")
        err = "0" if name == ORACLE else f"{np.abs(p - p_or_test).mean():.3f}"
        out.append(f"| {name} | " + " | ".join(cells) + f" | {err} |")
    out += [
        "",
        "## Precision at the top of the risk list",
        "",
        "Leaver rate among the highest-risk 10% / 20% of carers (a fixed retention budget). "
        "Base rate is the expected hit rate when choosing at random.",
        "",
        "| Model | CV out-of-fold top 10% | top 20% | Test top 10% | top 20% |",
        "|---|---|---|---|---|",
    ]
    oof_all = {**oof, ORACLE: p_or_train}
    for name in [*models, ORACLE]:
        cells = [
            f"{precision_at_top(yy, pp, s):.0%}"
            for yy, pp in ((y, oof_all[name]), (yt, test_preds[name]))
            for s in (0.1, 0.2)
        ]
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append(f"| {BASE_RATE} | {y.mean():.0%} | {y.mean():.0%} | {yt.mean():.0%} "
               f"| {yt.mean():.0%} |")  # fmt: skip
    out += [
        "",
        "## Calibration (out-of-fold, first CV repeat, 10 quantile bins)",
        "",
        "| Model | Mean predicted | Observed rate | Worst bin gap | Error vs truth |",
        "|---|---|---|---|---|",
    ]
    for name in models:
        t = calibration_table(y, oof[name])
        gap = (t.predicted - t.observed).abs().max()
        out.append(
            f"| {name} | {oof[name].mean():.3f} | {y.mean():.3f} | {gap:.3f} "
            f"| {np.abs(oof[name] - p_or_train).mean():.3f} |"
        )
    out += [
        "",
        "![ROC and PR curves](../figures/tier3_roc_pr.png)",
        "",
        "![Calibration](../figures/tier3_calibration.png)",
        "",
    ]
    for p in (FIG_CURVES, RESULTS):
        p.parent.mkdir(parents=True, exist_ok=True)
    chart_curves(y, oof, p_or_train)
    chart_calibration(y, oof, p_or_train)
    RESULTS.write_text("\n".join(out), encoding="utf-8")
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
