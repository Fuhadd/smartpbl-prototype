"""Evidence grounding: is each flag's quoted evidence actually in the (redacted) note?

Three tiers, cheapest and strictest first:
  1. exact       - verbatim substring.
  2. normalised  - same after case-folding and whitespace collapse (offsets mapped back).
  3. fuzzy       - best-aligned window via rapidfuzz partial_ratio >= FUZZY_THRESHOLD,
                   only for evidence of >= MIN_FUZZY_WORDS words (short spans match anything).
Otherwise the flag is ungrounded: possibly hallucinated, so it is rejected from auto-acceptance.
Ground against the redacted text: that is what the model saw and quoted.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 90.0  # calibrated on dev, see ADR-009 in docs/DECISIONS.md
MIN_FUZZY_WORDS = 3


class GroundingStatus(StrEnum):
    EXACT = "exact"
    NORMALISED = "normalised"
    FUZZY = "fuzzy"
    UNGROUNDED = "ungrounded"


@dataclass(frozen=True)
class Grounding:
    status: GroundingStatus
    score: float  # 100 for exact/normalised; partial_ratio for fuzzy/ungrounded
    start: int | None  # span in the source text (for highlighting in the review UI)
    end: int | None

    @property
    def grounded(self) -> bool:
        return self.status is not GroundingStatus.UNGROUNDED


def _normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Case-fold and collapse whitespace; return the index map back into `text`."""
    chars: list[str] = []
    index: list[int] = []
    prev_space = True  # also strips leading whitespace
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            chars.append(" ")
            prev_space = True
        else:
            chars.extend(ch.casefold())
            prev_space = False
        index.extend([i] * (len(chars) - len(index)))
    while chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


def _snap_to_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a span to whole words: fuzzy alignment windows can start or end mid-word."""
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def ground(evidence: str, source: str, threshold: float = FUZZY_THRESHOLD) -> Grounding:
    pos = source.find(evidence)
    if evidence and pos >= 0:
        return Grounding(GroundingStatus.EXACT, 100.0, pos, pos + len(evidence))

    norm_src, index = _normalise_with_map(source)
    norm_ev, _ = _normalise_with_map(evidence)
    if not norm_ev:
        return Grounding(GroundingStatus.UNGROUNDED, 0.0, None, None)

    pos = norm_src.find(norm_ev)
    if pos >= 0:
        end = pos + len(norm_ev) - 1
        return Grounding(GroundingStatus.NORMALISED, 100.0, index[pos], index[end] + 1)

    alignment = fuzz.partial_ratio_alignment(norm_ev, norm_src)
    score = alignment.score if alignment else 0.0
    long_enough = len(re.findall(r"\S+", norm_ev)) >= MIN_FUZZY_WORDS
    if alignment and long_enough and score >= threshold:
        start, end = _snap_to_words(
            source, index[alignment.dest_start], index[alignment.dest_end - 1] + 1
        )
        return Grounding(GroundingStatus.FUZZY, round(score, 1), start, end)
    return Grounding(GroundingStatus.UNGROUNDED, round(score, 1), None, None)
