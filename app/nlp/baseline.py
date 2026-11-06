"""Keyword/rules baseline extractor: the comparison point for the LLM.

Same output schema as the LLM (`Extraction`), so evaluation compares like for like.
Rules: per-category regex lexicon (each pattern carries a severity), optional context
words in the same sentence, and NegEx-style negation (a cue up to 5 tokens before the
trigger, scope cut at 'but'/'however'). The first matching pattern in priority order
sets a category's severity. Confidence is a constant: rules have no calibrated
uncertainty.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.nlp.schemas import Extraction, MedicationStatus, RiskCategory, RiskFlag, Severity

BASELINE_VERSION = "rules-v1"
CONFIDENCE = 0.7
NEGATION_WINDOW = 5
EVIDENCE_MAX_WORDS = 30
EVIDENCE_WINDOW = 6

C, S, M = RiskCategory, Severity, MedicationStatus

NEGATION_CUES = frozenset({"no", "not", "nil", "denies", "denied", "without", "none", "never"})
_SCOPE_TERMINATOR = re.compile(r"\b(?:but|however|although|though)\b|;", re.IGNORECASE)
# "NHS no 999...", "tel no", "room no 4": "no" meaning "number" is not a negation (v1 fix).
_NUMBER_NO = re.compile(
    r"\b(?:nhs|tel|phone|room|flat|ref)\.? no\b|\bno\.?\s*(?=[<\d])", re.IGNORECASE
)
_MED_CONTEXT = re.compile(
    r"\b(?:med|meds|medication|medicine|tablets?|pills?|dose|doses|mar|blister|"
    r"paracetamol|laxative|inhaler|insulin|cream)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    severity: Severity
    negatable: bool = True  # False when the pattern itself contains the negation ("not eaten")
    context: re.Pattern[str] | None = None  # must also appear in the same sentence
    check: Callable[[re.Match[str]], bool] | None = None  # extra test on the match itself


def _r(
    pattern: str,
    severity: Severity,
    negatable: bool = True,
    context: re.Pattern[str] | None = None,
    check: Callable[[re.Match[str]], bool] | None = None,
) -> Rule:
    return Rule(re.compile(pattern, re.IGNORECASE), severity, negatable, context, check)


def _minutes(hhmm: str) -> int:
    h, m = re.split(r"[:.]", hhmm)
    return int(h) * 60 + int(m)


def _arrived_after_scheduled(m: re.Match[str]) -> bool:
    return _minutes(m["arrived"]) > _minutes(m["scheduled"])


# Ordered by priority within each category: more specific patterns first.
RULES: dict[RiskCategory, list[Rule]] = {
    C.FALLS: [
        _r(r"\b(?:nearly|almost) fell\b|\bnear miss\b", S.MEDIUM),
        _r(r"\b(?:had a fall|fell|fallen|falls?|slipped|tripped)\b", S.HIGH),
        _r(r"\bfound on (?:the )?floor\b", S.HIGH),
        _r(
            r"\b(?:sat|sitting|lying|laid|found) on the (?:\w+ )?floor\b|\bwent down\b", S.HIGH
        ),  # v1
        _r(r"\bunsteady\b|\bwobbl\w*", S.MEDIUM),
    ],
    C.MEDICATION: [
        _r(
            r"\bnot (?:been )?(?:given|delivered|administered)\b",
            S.HIGH,
            negatable=False,
            context=_MED_CONTEXT,
        ),
        _r(r"\b(?:refus\w*|declin\w*)\b", S.MEDIUM, context=_MED_CONTEXT),
        _r(r"\bmissed\b", S.MEDIUM, context=_MED_CONTEXT),
        _r(r"\bfound (?:\w+ )?(?:tablets?|pills?|meds)\b", S.MEDIUM),  # v1: dropped/missed doses
        _r(r"\bonly took\b|\bspat\b", S.LOW, context=_MED_CONTEXT),
    ],
    C.NUTRITION_HYDRATION: [
        _r(r"(?:\bnot|n't) (?:eaten|drunk|had anything)\b", S.HIGH, negatable=False),
        _r(r"\bdehydrat\w*|\burine (?:was )?dark\b|\bdark urine\b", S.HIGH),
        _r(r"\bdrank (?:very )?little\b", S.HIGH),
        _r(r"\bpoor (?:appetite|intake|diet)\b|\bnot (?:eating|drinking)\b", S.MEDIUM),
        _r(r"\buntouched\b|\b(?:weight loss|lost weight)\b", S.MEDIUM),
        _r(
            r"\b(?:lips? (?:are |look |looks )?dry|dry lips|(?:isn't|is not|not) thirsty)\b",
            S.MEDIUM,
            negatable=False,
        ),  # v1
        _r(r"\bfridge (?:\w+ )?empty\b|\bout of date\b", S.LOW),  # v1
    ],
    C.SKIN_INTEGRITY: [
        _r(r"\bpressure (?:sore|ulcer|damage|area)s?\b", S.HIGH),
        _r(
            r"\b(?:did not|does not|didn't|not) blanch\w*|\bnon-?blanching\b",
            S.HIGH,
            negatable=False,
        ),
        _r(r"\bskin (?:tear|break|broken)\b", S.MEDIUM),
        _r(r"\bred(?:ness)? (?:area|patch|mark)\b|\bredness\b", S.MEDIUM),
        _r(
            r"\b(?:heels?|sacrum|bottom|hips?|elbows?|skin) (?:looks?|appears?|is|are) (?:very )?(?:red|sore)\b",
            S.MEDIUM,
        ),  # v1
    ],
    C.MOOD_BEHAVIOUR: [
        _r(r"\bsuicid\w*|\bself[- ]harm\w*|\bwants? to die\b", S.HIGH),
        _r(r"\blow (?:in )?mood\b|\bdepress\w*", S.MEDIUM),
        _r(
            r"\b(?:confus\w*|agitat\w*|aggressi\w*|disorientat\w*|tearful|withdrawn|distressed)\b",
            S.MEDIUM,
        ),
        _r(
            r"(?:\bnot|n't) (?:got |been )?(?:dressed|washed|out of bed)\b",
            S.MEDIUM,
            negatable=False,
        ),  # v1: self-neglect
        _r(r"\bquieter than (?:usual|normal)\b", S.LOW),
    ],
    C.SAFEGUARDING: [
        _r(r"\bunexplained (?:bruis\w*|injur\w*|marks?)\b", S.HIGH),
        _r(r"\babus\w*|\bsafeguarding\b", S.HIGH),
        _r(r"\b(?:money|cash|pension) (?:missing|taken)\b|\basking .{0,25}for money\b", S.HIGH),
        _r(
            r"\b(?:takes?|took|keeps?|kept|has) (?:her|his) (?:bank )?card\b", S.HIGH
        ),  # v1: financial
        _r(r"\b(?:frightened|scared|afraid)\b", S.MEDIUM),
    ],
    C.MISSED_LATE_VISIT: [
        _r(
            r"\bmissed (?:call|visit)\b|\b(?:call|visit) (?:was )?missed\b|\bno carer attended\b",
            S.HIGH,
            negatable=False,
        ),
        _r(
            r"\b(?:arrived|running|was|visit) late\b|\b\d+ ?min(?:ute)?s late\b|\blate (?:arrival|visit|call)\b",
            S.MEDIUM,
        ),
        _r(  # v1: "got here at 9:40 for the 8:30 call" -> compare times
            r"\b(?:got here|arrived|attended) at (?P<arrived>\d{1,2}[:.]\d{2}) for the (?P<scheduled>\d{1,2}[:.]\d{2})",
            S.MEDIUM,
            check=_arrived_after_scheduled,
        ),
        _r(r"\bcall cut short\b|\bshortened (?:call|visit)\b", S.LOW),
    ],
}

# Medication status, highest priority first. Partial > refused > missed > taken.
_STATUS_RULES: list[tuple[MedicationStatus, Rule]] = [
    (M.PARTIAL, _r(r"\bonly took\b|\bspat\b", S.LOW, context=_MED_CONTEXT)),
    (M.REFUSED, _r(r"\b(?:refus\w*|declin\w*)\b", S.MEDIUM, context=_MED_CONTEXT)),
    (
        M.MISSED,
        _r(
            r"\bmissed\b|\bnot (?:been )?(?:given|taken|delivered)\b|\bfound (?:\w+ )?(?:tablets?|pills?)\b",
            S.MEDIUM,
            negatable=False,
            context=_MED_CONTEXT,
        ),
    ),
    (
        M.TAKEN,
        _r(r"\b(?:taken|given|took|administered)\b|\bas per mar\b", S.LOW, context=_MED_CONTEXT),
    ),
]

_SEVERITY_RANK = {S.LOW: 0, S.MEDIUM: 1, S.HIGH: 2}


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?:\s+|$)", text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _is_negated(sentence: str, trigger_start: int) -> bool:
    before = sentence[:trigger_start]
    terminators = list(_SCOPE_TERMINATOR.finditer(before))
    if terminators:
        before = before[terminators[-1].end() :]
    before = _NUMBER_NO.sub(" ", before)
    tokens = re.findall(r"[a-z']+", before.lower())[-NEGATION_WINDOW:]
    return any(t in NEGATION_CUES for t in tokens)


def _evidence(text: str, sent: tuple[int, int], match: re.Match[str]) -> str:
    """The containing sentence, or a word window if the 'sentence' is a run-on note."""
    s_start, s_end = sent
    sentence = text[s_start:s_end]
    if len(sentence.split()) <= EVIDENCE_MAX_WORDS:
        return sentence.strip()
    words = list(re.finditer(r"\S+", sentence))
    hit = next(i for i, w in enumerate(words) if w.end() > match.start())
    lo, hi = max(0, hit - EVIDENCE_WINDOW), min(len(words) - 1, hit + EVIDENCE_WINDOW)
    return sentence[words[lo].start() : words[hi].end()]


def _first_match(text: str, rule: Rule) -> tuple[tuple[int, int], re.Match[str]] | None:
    for span in _sentence_spans(text):
        sentence = text[span[0] : span[1]]
        if rule.context and not rule.context.search(sentence):
            continue
        for m in rule.pattern.finditer(sentence):
            if rule.check and not rule.check(m):
                continue
            if not (rule.negatable and _is_negated(sentence, m.start())):
                return span, m
    return None


def medication_status(text: str) -> MedicationStatus:
    for status, rule in _STATUS_RULES:
        if _first_match(text, rule):
            return status
    return M.NOT_MENTIONED


def extract(text: str) -> Extraction:
    flags: list[RiskFlag] = []
    for category, rules in RULES.items():
        for rule in rules:
            found = _first_match(text, rule)
            if found:
                span, m = found
                flags.append(
                    RiskFlag(
                        category=category,
                        evidence=_evidence(text, span, m),
                        severity=rule.severity,
                        confidence=CONFIDENCE,
                    )
                )
                break
    names = ", ".join(f.category.value for f in flags)
    return Extraction(
        risk_flags=flags,
        medication_status=medication_status(text),
        follow_up_required=any(_SEVERITY_RANK[f.severity] >= 1 for f in flags),
        summary=f"Rule-based ({BASELINE_VERSION}): {len(flags)} risk flag(s)"
        + (f": {names}." if flags else "."),
    )
