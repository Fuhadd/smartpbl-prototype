"""Evaluation of extraction systems against gold labels (Step 1.9).

All metrics are computed per note at category level (a note either has a falls flag or it
doesn't), which is what the review queue acts on. A failed extraction counts as "no flags":
every gold flag in that note is a false negative, so failures can't flatter recall.
"""

import random
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.nlp import baseline
from app.nlp.dataset import GoldFlag, LabelledNote
from app.nlp.ground import ground
from app.nlp.metrics import CategoryReport, category_report
from app.nlp.route import decide
from app.nlp.schemas import Extraction, RiskCategory, RiskFlag, Severity

NONE = "no_gold_flag"  # confusion row: predicted, but no gold flag (pure false positive)
MISSED = "not_found"  # confusion column: gold flag with no matching prediction
_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


@dataclass(frozen=True)
class Prediction:
    """One system's output for one note."""

    note_id: str
    redacted_text: str
    extraction: Extraction | None  # None: failed after retries
    attempts: int = 1
    latency_ms: float | None = None


@dataclass(frozen=True)
class Routing:
    """The full pipeline (LLM + rules safety net + routing), as deployed."""

    notes_reviewed: int
    gold_flags: int
    escaped: int  # gold flags with no flag of that category from either source
    high_escaped: int
    high_total: int
    auto_accepted: int
    auto_accepted_false_positive: int


@dataclass(frozen=True)
class EvalResult:
    system: str
    n_notes: int
    n_gold_flags: int
    report: CategoryReport
    valid_first_try: int
    valid_final: int
    grounding: dict[str, int]  # status -> predicted flag count
    severity_matches: int
    severity_pairs: int
    latencies_ms: list[float]
    negated_mentions: int
    negated_false_positives: int
    subset_recall: dict[str, tuple[int, int]]  # tag -> (tp, gold flags)
    ci: dict[str, tuple[float, float]] = field(default_factory=dict)  # bootstrap 95%
    gold_sets: list[set[RiskCategory]] = field(default_factory=list)  # per note, for pairing
    pred_sets: list[set[RiskCategory]] = field(default_factory=list)
    confusion: dict[str, Counter[str]] = field(default_factory=dict)
    routing: Routing | None = None

    @property
    def grounding_rate(self) -> float:
        total = sum(self.grounding.values())
        return 1 - self.grounding.get("ungrounded", 0) / total if total else 1.0

    @property
    def severity_agreement(self) -> float:
        return self.severity_matches / self.severity_pairs if self.severity_pairs else 0.0

    def latency(self, q: float) -> float | None:
        if not self.latencies_ms:
            return None
        if len(self.latencies_ms) == 1:
            return self.latencies_ms[0]
        return statistics.quantiles(self.latencies_ms, n=100, method="inclusive")[
            round(q * 100) - 1
        ]


def _max_severity(flags: Sequence[GoldFlag | RiskFlag]) -> dict[RiskCategory, Severity]:
    out: dict[RiskCategory, Severity] = {}
    for f in flags:
        if f.category not in out or _RANK[f.severity] > _RANK[out[f.category]]:
            out[f.category] = f.severity
    return out


Span = tuple[int | None, int | None]


def _overlaps(a: Span, b: Span) -> bool:
    (a0, a1), (b0, b1) = a, b
    if a0 is None or a1 is None or b0 is None or b1 is None:
        return False
    return a0 < b1 and b0 < a1


def _confusion(gold: LabelledNote, pred: Prediction, out: dict[str, Counter[str]]) -> None:
    """Category confusion via evidence overlap: a gold flag the system filed under another
    category shows up off the diagonal (e.g. missed_late_visit -> safeguarding)."""
    text = pred.redacted_text
    flags = pred.extraction.risk_flags if pred.extraction else []
    pred_spans = [(f.category, (g.start, g.end)) for f in flags for g in [ground(f.evidence, text)]]
    pred_cats = {f.category for f in flags}
    gold_cats = {f.category for f in gold.gold.risk_flags}
    explained: set[int] = set()
    for gf in gold.gold.risk_flags:
        row = out.setdefault(gf.category.value, Counter())
        if gf.category in pred_cats:
            row[gf.category.value] += 1
            continue
        g = ground(gf.evidence, text)
        hits = [i for i, (_, span) in enumerate(pred_spans) if _overlaps(span, (g.start, g.end))]
        hits = [i for i in hits if pred_spans[i][0] not in gold_cats]
        for i in hits:
            row[pred_spans[i][0].value] += 1
        explained.update(hits)
        if not hits:
            row[MISSED] += 1
    for i, (cat, _) in enumerate(pred_spans):
        if cat not in gold_cats and i not in explained:
            out.setdefault(NONE, Counter())[cat.value] += 1


def _routing(gold: Sequence[LabelledNote], preds: dict[str, Prediction]) -> Routing:
    reviewed = escaped = high_escaped = high_total = auto = auto_fp = n_gold = 0
    for g in gold:
        p = preds[g.note.note_id]
        d = decide(p.extraction, p.redacted_text, baseline.extract(p.redacted_text))
        reviewed += d.review_required
        cats = {f.flag.category for f in d.flags}
        gold_cats = {f.category for f in g.gold.risk_flags}
        for gf in g.gold.risk_flags:
            n_gold += 1
            high = gf.severity is Severity.HIGH
            high_total += high
            if gf.category not in cats:
                escaped += 1
                high_escaped += high
        for f in d.flags:
            if not f.needs_review:
                auto += 1
                auto_fp += f.flag.category not in gold_cats
    return Routing(reviewed, n_gold, escaped, high_escaped, high_total, auto, auto_fp)


def bootstrap_ci(
    gold_sets: Sequence[set[RiskCategory]],
    pred_sets: Sequence[set[RiskCategory]],
    *,
    n_boot: int = 1000,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """95% percentile intervals for micro P/R/F1, resampling notes with replacement.
    With ~40 test notes the intervals are wide; differences inside them aren't evidence."""
    rng = random.Random(seed)
    idx = range(len(gold_sets))
    samples: dict[str, list[float]] = {"precision": [], "recall": [], "f1": []}
    for _ in range(n_boot):
        pick = [rng.choice(idx) for _ in idx]
        m = category_report([gold_sets[i] for i in pick], [pred_sets[i] for i in pick]).micro
        samples["precision"].append(m.precision)
        samples["recall"].append(m.recall)
        samples["f1"].append(m.f1)
    out = {}
    for k, v in samples.items():
        v.sort()
        out[k] = (v[int(0.025 * n_boot)], v[int(0.975 * n_boot) - 1])
    return out


@dataclass(frozen=True)
class PairedDiff:
    """System A minus system B on the same notes."""

    metric: str
    diff: float
    low: float
    high: float
    p_not_better: float  # share of resamples where A <= B (a one-sided bootstrap p-value)


def paired_bootstrap(
    a: "EvalResult", b: "EvalResult", *, n_boot: int = 2000, seed: int = 42
) -> list[PairedDiff]:
    """Resample notes once per round and score both systems on the same resample, so
    note difficulty cancels out. Far more sensitive than comparing two separate CIs."""
    if a.gold_sets != b.gold_sets:
        raise ValueError("systems were evaluated on different notes")
    rng = random.Random(seed)
    n = len(a.gold_sets)
    diffs: dict[str, list[float]] = {"recall": [], "f1": []}
    for _ in range(n_boot):
        pick = [rng.randrange(n) for _ in range(n)]
        g = [a.gold_sets[i] for i in pick]
        ma = category_report(g, [a.pred_sets[i] for i in pick]).micro
        mb = category_report(g, [b.pred_sets[i] for i in pick]).micro
        diffs["recall"].append(ma.recall - mb.recall)
        diffs["f1"].append(ma.f1 - mb.f1)
    out = []
    for metric, v in diffs.items():
        v.sort()
        point = getattr(a.report.micro, metric) - getattr(b.report.micro, metric)
        low, high = v[int(0.025 * n_boot)], v[int(0.975 * n_boot) - 1]
        out.append(PairedDiff(metric, point, low, high, sum(x <= 0 for x in v) / n_boot))
    return out


def union_recall(a: "EvalResult", b: "EvalResult") -> float:
    """Recall if both systems' flags are surfaced (the deployed safety-net design)."""
    union = [x | y for x, y in zip(a.pred_sets, b.pred_sets, strict=True)]
    return category_report(a.gold_sets, union).micro.recall


def evaluate(
    system: str,
    gold: Sequence[LabelledNote],
    preds: dict[str, Prediction],
    *,
    with_routing: bool = False,
    n_boot: int = 1000,
    seed: int = 42,
) -> EvalResult:
    missing = {g.note.note_id for g in gold} - preds.keys()
    if missing:
        raise ValueError(f"{system}: no prediction for {sorted(missing)[:5]}")

    gold_sets, pred_sets = [], []
    grounding: Counter[str] = Counter()
    sev_match = sev_pairs = neg_mentions = neg_fp = 0
    subset: dict[str, list[int]] = {}
    confusion: dict[str, Counter[str]] = {}
    for g in gold:
        p = preds[g.note.note_id]
        flags = p.extraction.risk_flags if p.extraction else []
        g_cats = {f.category for f in g.gold.risk_flags}
        p_cats = {f.category for f in flags}
        gold_sets.append(g_cats)
        pred_sets.append(p_cats)
        for f in flags:
            grounding[ground(f.evidence, p.redacted_text).status.value] += 1
        g_sev, p_sev = _max_severity(g.gold.risk_flags), _max_severity(flags)
        for c in g_cats & p_cats:
            sev_pairs += 1
            sev_match += g_sev[c] == p_sev[c]
        negated = set(g.negated) - g_cats  # mentioned only in the negative
        neg_mentions += len(negated)
        neg_fp += len(negated & p_cats)
        for tag in g.tags:
            s = subset.setdefault(tag, [0, 0])
            s[0] += len(g_cats & p_cats)
            s[1] += len(g_cats)
        _confusion(g, p, confusion)

    return EvalResult(
        system=system,
        n_notes=len(gold),
        n_gold_flags=sum(len(s) for s in gold_sets),
        report=category_report(gold_sets, pred_sets),
        valid_first_try=sum(
            1 for g in gold if (p := preds[g.note.note_id]).extraction and p.attempts == 1
        ),
        valid_final=sum(1 for g in gold if preds[g.note.note_id].extraction is not None),
        grounding=dict(grounding),
        severity_matches=sev_match,
        severity_pairs=sev_pairs,
        latencies_ms=[
            p.latency_ms for g in gold if (p := preds[g.note.note_id]).latency_ms is not None
        ],
        negated_mentions=neg_mentions,
        negated_false_positives=neg_fp,
        subset_recall={k: (v[0], v[1]) for k, v in sorted(subset.items())},
        ci=bootstrap_ci(gold_sets, pred_sets, n_boot=n_boot, seed=seed),
        gold_sets=gold_sets,
        pred_sets=pred_sets,
        confusion=confusion,
        routing=_routing(gold, preds) if with_routing else None,
    )
