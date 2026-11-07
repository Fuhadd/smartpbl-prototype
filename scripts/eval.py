"""Evaluate LLM extraction against the rules baseline (Step 1.9).

Usage:
  uv run python -m scripts.eval --split dev
  uv run python -m scripts.eval --split test --final      # the one-off held-out evaluation

LLM predictions come from `scripts.run_extraction` (cached JSONL). The baseline is run
here on the same redacted text. Writes docs/results/tier1_eval_<split>.{md,json} and
charts in docs/figures/.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from app.nlp import baseline
from app.nlp.dataset import LabelledNote, read_jsonl
from app.nlp.evaluation import (
    MISSED,
    NONE,
    EvalResult,
    Prediction,
    evaluate,
    paired_bootstrap,
    union_recall,
)
from app.nlp.redact import redact
from app.nlp.schemas import Extraction, RiskCategory
from scripts.run_extraction import DATA_DIR, output_path

SEED = 42
N_BOOT = 1000
RESULTS_DIR = Path("docs/results")
FIGURES_DIR = Path("docs/figures")
DEFAULT_SYSTEMS = ["llama3.1:8b@v2", "qwen2.5:3b@v2"]
SHORT = {
    "falls": "falls",
    "medication": "medication",
    "nutrition_hydration": "nutrition",
    "skin_integrity": "skin",
    "mood_behaviour": "mood",
    "safeguarding": "safeguarding",
    "missed_late_visit": "late/missed",
    NONE: "(no gold flag)",
    MISSED: "(not found)",
}
# Categorical slots 1-4 of the validated reference palette (adjacent-pair CVD-safe on the
# light surface). Aqua and yellow are below 3:1 contrast: the Markdown tables are the relief.
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"


def load_llm(split: str, spec: str) -> tuple[dict[str, Prediction], dict[str, str]]:
    model, prompt = spec.split("@")
    path = output_path(split, model, prompt)
    if not path.exists():
        sys.exit(f"missing {path}: run scripts.run_extraction --split {split} --model {model}")
    preds, meta = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ext = Extraction.model_validate(r["extraction"]) if r["extraction"] else None
        preds[r["note_id"]] = Prediction(
            r["note_id"], r["redacted_text"], ext, r["attempts"], r.get("latency_ms")
        )
        if "model_digest" in r:
            meta = {
                "model": r["model"],
                "model_digest": r["model_digest"][:12],
                "prompt_version": r["prompt_version"],
                "prompt_sha256": r["prompt_sha256"][:12],
            }
    return preds, meta


def run_baseline(gold: list[LabelledNote]) -> dict[str, Prediction]:
    preds = {}
    for g in gold:
        text = redact(g.note.text).text
        t0 = time.perf_counter()
        ext = baseline.extract(text)
        ms = (time.perf_counter() - t0) * 1000
        preds[g.note.note_id] = Prediction(g.note.note_id, text, ext, 1, ms)
    return preds


def _pct(x: float) -> str:
    return f"{x:.3f}"


def _ms(x: float | None) -> str:
    return "n/a" if x is None else (f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.1f} ms")


def markdown(split: str, results: list[EvalResult], meta: dict[str, dict[str, str]]) -> str:
    r0 = results[0]
    out = [
        f"# Tier 1 evaluation — `{split}` split",
        "",
        f"- Notes: **{r0.n_notes}**; gold flags: **{r0.n_gold_flags}**; data seed {SEED} "
        f"(`scripts/generate_notes.py`); bootstrap: {N_BOOT} resamples of notes, seed {SEED}.",
        "- Matching is per note and category. Failed extractions count as no flags.",
        "- Synthetic data written by the same author as the rules and prompts: treat absolute "
        "numbers as optimistic (see `data/care_notes/DATA_CARD.md`).",
        "",
        "| System | Model digest | Prompt (sha) |",
        "|---|---|---|",
    ]
    for r in results:
        m = meta.get(r.system, {})
        prompt = f"{m['prompt_version']} ({m['prompt_sha256']})" if m else "n/a"
        out.append(
            f"| {r.system} | {m.get('model_digest', baseline.BASELINE_VERSION)} | {prompt} |"
        )
    out += [
        "",
        "## Overall",
        "",
        "| System | Micro P | Micro R (95% CI) | Micro F1 (95% CI) | Macro F1 | Severity agreement "
        "| Valid 1st try / final | Grounded | Latency p50 / p95 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m, ci = r.report.micro, r.ci
        out.append(
            f"| {r.system} | {_pct(m.precision)} "
            f"| {_pct(m.recall)} ({_pct(ci['recall'][0])}-{_pct(ci['recall'][1])}) "
            f"| {_pct(m.f1)} ({_pct(ci['f1'][0])}-{_pct(ci['f1'][1])}) "
            f"| {_pct(r.report.macro_f1)} | {_pct(r.severity_agreement)} "
            f"({r.severity_matches}/{r.severity_pairs}) "
            f"| {r.valid_first_try}/{r.n_notes} / {r.valid_final}/{r.n_notes} "
            f"| {r.grounding_rate:.1%} | {_ms(r.latency(0.5))} / {_ms(r.latency(0.95))} |"
        )
    out += ["", "## Per category (P / R / F1)", ""]
    out.append("| Category | Gold | " + " | ".join(r.system for r in results) + " |")
    out.append("|---|---|" + "---|" * len(results))
    for c in RiskCategory:
        cells = []
        for r in results:
            p = r.report.per_category[c]
            cells.append(f"{p.precision:.2f} / {p.recall:.2f} / {p.f1:.2f}")
        n = r0.report.per_category[c]
        out.append(f"| {c.value} | {n.tp + n.fn} | " + " | ".join(cells) + " |")
    out += ["", "## Robustness slices (recall)", ""]
    tags = sorted(t for t, (_, n) in r0.subset_recall.items() if n)
    out.append("| Slice | Gold flags | " + " | ".join(r.system for r in results) + " |")
    out.append("|---|---|" + "---|" * len(results))
    for t in tags:
        n = r0.subset_recall[t][1]
        out.append(
            f"| {t} | {n} | "
            + " | ".join(f"{r.subset_recall[t][0] / n:.2f}" for r in results)
            + " |"
        )
    out.append(
        "| negation false positives | "
        f"{r0.negated_mentions} negated mentions | "
        + " | ".join(f"{r.negated_false_positives}" for r in results)
        + " |"
    )
    rules = results[-1]
    out += [
        "",
        f"## Paired comparison against {rules.system} (2000 paired resamples)",
        "",
        "| System | Recall diff (95% CI) | P(not better) | F1 diff (95% CI) | P(not better) "
        "| Recall of LLM + rules (union) |",
        "|---|---|---|---|---|---|",
    ]
    for r in results[:-1]:
        rec, f1 = paired_bootstrap(r, rules, seed=SEED)
        out.append(
            f"| {r.system} | {rec.diff:+.3f} ({rec.low:+.3f} to {rec.high:+.3f}) "
            f"| {rec.p_not_better:.3f} | {f1.diff:+.3f} ({f1.low:+.3f} to {f1.high:+.3f}) "
            f"| {f1.p_not_better:.3f} | {union_recall(r, rules):.3f} |"
        )
    routed = [r for r in results if r.routing]
    if routed:
        out += [
            "",
            "## Deployed pipeline: LLM + rules safety net + routing",
            "",
            "| System | Notes to review | Gold flags escaped (no flag at all) | High-severity "
            "escaped | Auto-accepted | Auto-accepted false positives |",
            "|---|---|---|---|---|---|",
        ]
        for r in routed:
            rt = r.routing
            assert rt is not None
            out.append(
                f"| {r.system} | {rt.notes_reviewed}/{r.n_notes} "
                f"({rt.notes_reviewed / r.n_notes:.0%}) | {rt.escaped}/{rt.gold_flags} "
                f"({rt.escaped / rt.gold_flags:.1%}) | {rt.high_escaped}/{rt.high_total} "
                f"| {rt.auto_accepted} | {rt.auto_accepted_false_positive} |"
            )
    out += [
        "",
        "## Figures",
        "",
        f"![Recall per category](../figures/tier1_recall_{split}.png)",
        "",
        f"![Category confusion](../figures/tier1_confusion_{split}.png)",
        "",
    ]
    return "\n".join(out)


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelcolor=INK)


def recall_chart(split: str, results: list[EvalResult], path: Path) -> None:
    cats = list(RiskCategory)
    fig, ax = plt.subplots(figsize=(8, 4.6), facecolor=SURFACE)
    _style(ax)
    h = 0.8 / len(results)
    y = np.arange(len(cats))
    for i, r in enumerate(results):
        vals = [r.report.per_category[c].recall for c in cats]
        pos = y + (i - (len(results) - 1) / 2) * h
        ax.barh(pos, vals, height=h - 0.04, color=COLOURS[i], label=r.system, edgecolor=SURFACE)
    ax.set_yticks(y, [SHORT[c.value] for c in cats])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Recall (share of gold flags found)", color=MUTED)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    n = results[0].n_notes
    ax.set_title(
        f"Recall per risk category — {split} split, {n} notes, seed {SEED}",
        color=INK,
        loc="left",
        fontsize=11,
        pad=28,
    )
    ax.legend(
        frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(results), labelcolor=INK
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def confusion_chart(split: str, results: list[EvalResult], path: Path) -> None:
    rows = [c.value for c in RiskCategory] + [NONE]
    cols = [c.value for c in RiskCategory] + [MISSED]
    mats = [
        np.array([[r.confusion.get(a, {}).get(b, 0) for b in cols] for a in rows]) for r in results
    ]
    vmax = max(int(m.max()) for m in mats) or 1
    cmap = LinearSegmentedColormap.from_list(
        "blue", ["#ffffff", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
    )
    fig, axes = plt.subplots(
        1, len(results), figsize=(5.2 * len(results), 5.4), facecolor=SURFACE, squeeze=False
    )
    for ax, r, m in zip(axes[0], results, mats, strict=True):
        ax.imshow(m, cmap=cmap, vmin=0, vmax=vmax)
        for i in range(len(rows)):
            for j in range(len(cols)):
                if m[i, j]:
                    dark = m[i, j] > vmax * 0.55
                    colour = "#ffffff" if dark else INK
                    ax.text(j, i, m[i, j], ha="center", va="center", fontsize=9, color=colour)
        labels_c = [SHORT[c] for c in cols]
        labels_r = [SHORT[c] for c in rows]
        ax.set_xticks(range(len(cols)), labels_c, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(rows)), labels_r, fontsize=8)
        ax.set_xticks(np.arange(-0.5, len(cols)), minor=True)
        ax.set_yticks(np.arange(-0.5, len(rows)), minor=True)
        ax.grid(which="minor", color=SURFACE, linewidth=2)
        ax.tick_params(which="both", length=0, labelcolor=INK)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(r.system, color=INK, fontsize=10, loc="left")
        ax.set_xlabel("Predicted category", color=MUTED, fontsize=9)
        ax.set_ylabel("Gold category", color=MUTED, fontsize=9)
    fig.suptitle(
        f"Category confusion by evidence overlap — {split} split, {results[0].n_notes} notes",
        color=INK,
        x=0.01,
        ha="left",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def as_json(r: EvalResult) -> dict[str, object]:
    return {
        "system": r.system,
        "n_notes": r.n_notes,
        "n_gold_flags": r.n_gold_flags,
        "micro": {
            "tp": r.report.micro.tp,
            "fp": r.report.micro.fp,
            "fn": r.report.micro.fn,
            "precision": r.report.micro.precision,
            "recall": r.report.micro.recall,
            "f1": r.report.micro.f1,
        },
        "macro_f1": r.report.macro_f1,
        "ci95": r.ci,
        "per_category": {
            c.value: {"tp": p.tp, "fp": p.fp, "fn": p.fn, "f1": p.f1}
            for c, p in r.report.per_category.items()
        },
        "severity_agreement": r.severity_agreement,
        "valid_first_try": r.valid_first_try,
        "valid_final": r.valid_final,
        "grounding": r.grounding,
        "latency_ms": {"p50": r.latency(0.5), "p95": r.latency(0.95)},
        "negated_false_positives": r.negated_false_positives,
        "subset_recall": r.subset_recall,
        "confusion": {k: dict(v) for k, v in r.confusion.items()},
        "routing": vars(r.routing) if r.routing else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--systems", nargs="+", default=DEFAULT_SYSTEMS, help="model@prompt")
    ap.add_argument("--final", action="store_true", help="required for the test split")
    args = ap.parse_args()
    if len(args.systems) + 1 > len(COLOURS):
        sys.exit(f"at most {len(COLOURS) - 1} LLM systems per chart")
    if args.split == "test" and not args.final:
        sys.exit("Refusing to evaluate on test without --final (test is opened once).")

    gold = read_jsonl(DATA_DIR / f"{args.split}.jsonl")
    results, meta = [], {}
    for spec in args.systems:
        preds, meta[spec] = load_llm(args.split, spec)
        results.append(evaluate(spec, gold, preds, with_routing=True, n_boot=N_BOOT, seed=SEED))
    results.append(evaluate(baseline.BASELINE_VERSION, gold, run_baseline(gold), n_boot=N_BOOT))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"tier1_eval_{args.split}"
    (RESULTS_DIR / f"{stem}.md").write_text(markdown(args.split, results, meta), encoding="utf-8")
    (RESULTS_DIR / f"{stem}.json").write_text(
        json.dumps(
            {"split": args.split, "seed": SEED, "systems": [as_json(r) for r in results]},
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    recall_chart(args.split, results, FIGURES_DIR / f"tier1_recall_{args.split}.png")
    confusion_chart(args.split, results, FIGURES_DIR / f"tier1_confusion_{args.split}.png")
    print((RESULTS_DIR / f"{stem}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
