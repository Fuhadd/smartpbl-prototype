"""Rules baseline tests. Sentences are new (not copied from the generator templates), so these
test rule behaviour rather than restating the dataset."""

from pathlib import Path

import pytest

from app.nlp.baseline import extract, medication_status
from app.nlp.dataset import read_jsonl
from app.nlp.metrics import category_report
from app.nlp.redact import redact
from app.nlp.schemas import MedicationStatus, RiskCategory, Severity

C = RiskCategory


def categories(text: str) -> set[RiskCategory]:
    return {f.category for f in extract(text).risk_flags}


@pytest.mark.parametrize(
    ("text", "absent"),
    [
        ("Denies any falls this week.", C.FALLS),
        ("No signs of confusion today.", C.MOOD_BEHAVIOUR),
        ("Skin intact, no redness seen.", C.SKIN_INTEGRITY),
        ("Took all tablets, nil missed doses.", C.MEDICATION),
    ],
)
def test_negation_suppresses_flag(text: str, absent: RiskCategory) -> None:
    assert absent not in categories(text)


def test_negation_scope_ends_at_but() -> None:
    assert C.FALLS in categories("No injury seen but she fell in the garden.")


def test_number_abbreviation_is_not_negation() -> None:
    assert C.MOOD_BEHAVIOUR in categories(
        "Call to <PERSON> (NHS no <UK_NHS>) confused and agitated"
    )


def test_pattern_containing_negation_still_fires() -> None:
    flags = extract("She hasn't eaten since breakfast.").risk_flags
    assert [(f.category, f.severity) for f in flags] == [(C.NUTRITION_HYDRATION, Severity.HIGH)]


def test_medication_needs_medication_context() -> None:
    assert C.MEDICATION not in categories("Refused to have a shower this morning.")
    assert C.MEDICATION in categories("Refused her inhaler this morning.")


@pytest.mark.parametrize(
    ("text", "late"),
    [
        ("Arrived at 10:15 for the 10:00 call.", True),
        ("Arrived at 9:55 for the 10:00 call.", False),
    ],
)
def test_lateness_compares_times(text: str, late: bool) -> None:
    assert (C.MISSED_LATE_VISIT in categories(text)) is late


def test_late_husband_is_not_a_late_visit() -> None:
    assert C.MISSED_LATE_VISIT not in categories("Talked about her late husband over tea.")


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("Meds given as per MAR.", MedicationStatus.TAKEN),
        ("Only took half of her tablets.", MedicationStatus.PARTIAL),
        ("Declined evening medication.", MedicationStatus.REFUSED),
        ("All medication taken, no refusals.", MedicationStatus.TAKEN),
        ("Watched the news together.", MedicationStatus.NOT_MENTIONED),
    ],
)
def test_medication_status(text: str, status: MedicationStatus) -> None:
    assert medication_status(text) is status


def test_evidence_is_substring_and_bounded_in_run_on_note() -> None:
    filler = " ".join(["helped with the washing up and chatted"] * 6)
    text = f"{filler} she slipped by the back door {filler}"
    (flag,) = extract(text).risk_flags
    assert flag.evidence in text
    assert "slipped" in flag.evidence
    assert len(flag.evidence.split()) <= 13


def test_no_risk_note() -> None:
    result = extract("Made lunch and put the washing out.")
    assert result.risk_flags == []
    assert result.follow_up_required is False


def test_dev_regression_floor() -> None:
    """Tuned on dev, so this is an optimistic regression check, not a performance claim.
    Measured 2026-11-06 (rules-v1, redacted dev): micro P=1.000 R=0.972 F1=0.986."""
    notes = read_jsonl(Path("data/care_notes/dev.jsonl"))
    preds = [extract(redact(n.note.text).text) for n in notes]
    report = category_report(
        [{f.category for f in n.gold.risk_flags} for n in notes],
        [{f.category for f in p.risk_flags} for p in preds],
    )
    assert report.micro.f1 >= 0.95
    assert report.micro.precision >= 0.95
