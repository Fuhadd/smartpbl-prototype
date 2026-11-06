"""Set-based classification metrics for multi-label risk flags (per note, per category)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.nlp.schemas import RiskCategory


@dataclass(frozen=True)
class PRF:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass(frozen=True)
class CategoryReport:
    per_category: dict[RiskCategory, PRF]
    micro: PRF  # pooled counts: dominated by frequent categories
    macro_f1: float  # unweighted mean of per-category F1: every category counts equally


def category_report(
    gold: Sequence[Iterable[RiskCategory]], pred: Sequence[Iterable[RiskCategory]]
) -> CategoryReport:
    """Each element is the set of categories flagged for one note."""
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have one entry per note")
    counts = {c: [0, 0, 0] for c in RiskCategory}
    for g_items, p_items in zip(gold, pred, strict=True):
        g, p = set(g_items), set(p_items)
        for c in g & p:
            counts[c][0] += 1
        for c in p - g:
            counts[c][1] += 1
        for c in g - p:
            counts[c][2] += 1
    per = {c: PRF(*v) for c, v in counts.items()}
    micro = PRF(*(sum(v[i] for v in counts.values()) for i in range(3)))
    macro_f1 = sum(m.f1 for m in per.values()) / len(per)
    return CategoryReport(per_category=per, micro=micro, macro_f1=macro_f1)
