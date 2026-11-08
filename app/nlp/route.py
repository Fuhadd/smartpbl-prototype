"""Human-in-the-loop routing: decide which flags a coordinator must review.

Nothing is silently discarded. Every flag ends up either auto-accepted or in the review
queue with explicit reasons. Rules (any one sends a flag to review):
  - severity high                      : potential harm needs a human decision
  - category safeguarding              : policy; always a human decision
  - grounding not exact/normalised     : fuzzy evidence is less trustworthy
  - ungrounded evidence                : possibly hallucinated; rejected from auto-accept
  - confidence < CONFIDENCE_THRESHOLD  : required by spec, though LLM confidence is
                                         poorly spread (see ADR-013)
  - baseline-only category             : rules found a risk the LLM did not (safety net)
Extraction failure sends the whole note to review.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.nlp.ground import Grounding, GroundingStatus, ground
from app.nlp.schemas import Extraction, RiskCategory, RiskFlag, Severity

CONFIDENCE_THRESHOLD = 0.7


class ReviewReason(StrEnum):
    HIGH_SEVERITY = "high_severity"
    SAFEGUARDING = "safeguarding_policy"
    FUZZY_EVIDENCE = "fuzzy_evidence"
    UNGROUNDED = "ungrounded_evidence"
    LOW_CONFIDENCE = "low_confidence"
    BASELINE_ONLY = "baseline_only"
    EXTRACTION_FAILED = "extraction_failed"


@dataclass(frozen=True)
class FlagDecision:
    flag: RiskFlag
    grounding: Grounding
    source: str  # "llm" or "baseline"
    reasons: tuple[ReviewReason, ...]

    @property
    def needs_review(self) -> bool:
        return bool(self.reasons)


@dataclass(frozen=True)
class NoteDecision:
    flags: tuple[FlagDecision, ...]
    note_reasons: tuple[ReviewReason, ...]  # note-level, e.g. extraction failed

    @property
    def review_required(self) -> bool:
        return bool(self.note_reasons) or any(f.needs_review for f in self.flags)

    @property
    def auto_accepted(self) -> tuple[RiskFlag, ...]:
        return tuple(f.flag for f in self.flags if not f.needs_review)


def _flag_reasons(flag: RiskFlag, grounding: Grounding) -> tuple[ReviewReason, ...]:
    reasons = []
    if not grounding.grounded:
        reasons.append(ReviewReason.UNGROUNDED)
    elif grounding.status is GroundingStatus.FUZZY:
        reasons.append(ReviewReason.FUZZY_EVIDENCE)
    if flag.severity is Severity.HIGH:
        reasons.append(ReviewReason.HIGH_SEVERITY)
    if flag.category is RiskCategory.SAFEGUARDING:
        reasons.append(ReviewReason.SAFEGUARDING)
    if flag.confidence < CONFIDENCE_THRESHOLD:
        reasons.append(ReviewReason.LOW_CONFIDENCE)
    return tuple(reasons)


def decide(
    llm: Extraction | None, redacted_text: str, baseline: Extraction | None = None
) -> NoteDecision:
    """`llm` is None when extraction failed after retries."""
    decisions: list[FlagDecision] = []
    for flag in llm.risk_flags if llm else ():
        g = ground(flag.evidence, redacted_text)
        decisions.append(FlagDecision(flag, g, "llm", _flag_reasons(flag, g)))

    llm_categories = {f.category for f in llm.risk_flags} if llm else set()
    for flag in baseline.risk_flags if baseline else ():
        if flag.category not in llm_categories:
            g = ground(flag.evidence, redacted_text)
            reasons = (ReviewReason.BASELINE_ONLY, *_flag_reasons(flag, g))
            decisions.append(FlagDecision(flag, g, "baseline", reasons))

    note_reasons = () if llm else (ReviewReason.EXTRACTION_FAILED,)
    return NoteDecision(flags=tuple(decisions), note_reasons=note_reasons)
