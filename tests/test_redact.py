"""Redaction tests. All identifiers are synthetic (ZZ/Z postcode areas, Ofcom drama numbers,
NHS 999 test range, placeholder names)."""

from pathlib import Path

import pytest

from app.nlp.dataset import LabelledNote, read_jsonl
from app.nlp.redact import RedactedText, redact

DATA = Path("data/care_notes")


@pytest.mark.parametrize(
    "postcode", ["Z1 1ZZ", "Z12 3ZZ", "Z1Z 1ZZ", "ZZ1 1ZZ", "ZZ12 3ZZ", "ZZ1Z 1ZZ", "zz15 6fq"]
)
def test_uk_postcode_formats_masked(postcode: str) -> None:
    out = redact(f"Moved to a flat at {postcode} last week.")
    assert postcode not in out.text


@pytest.mark.parametrize("nhs", ["999 123 4567", "9991234567", "999-123-4567"])
def test_nhs_like_numbers_masked_without_checksum(nhs: str) -> None:
    out = redact(f"NHS no {nhs} on the care plan.")
    assert nhs not in out.text
    assert "<UK_NHS>" in out.text


@pytest.mark.parametrize(
    "phone", ["07700 900123", "+44 7700 900123", "07700900123", "01632 960123"]
)
def test_uk_phone_numbers_masked(phone: str) -> None:
    out = redact(f"Daughter rang on {phone} this morning.")
    assert phone not in out.text
    assert "<PHONE_NUMBER>" in out.text


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Visited Mrs Sampleton this morning.", "Sampleton"),
        ("call to ms dummyford, all well.", "dummyford"),  # lowercase: NER alone misses
        ("Her daughter Delta Fakename rang.", "Delta Fakename"),  # first name is a common word
    ],
)
def test_names_masked(text: str, name: str) -> None:
    assert name not in redact(text).text


def test_street_address_masked() -> None:
    out = redact("Visited at 14 Fictional Avenue, ZZ3 4AB.")
    assert "Fictional Avenue" not in out.text
    assert "<UK_STREET_ADDRESS>" in out.text


def test_known_names_catch_what_generic_recognisers_miss() -> None:
    text = "daughter delta placeholder rang before the visit"
    assert "delta placeholder" in redact(text).text  # documented residual gap
    assert "delta placeholder" not in redact(text, known_names=("Delta Placeholder",)).text


@pytest.mark.parametrize(
    "clinical",
    [
        "Got here at 9:40 for the 8:30 call, traffic on the ring road.",  # times are evidence
        "Client said her nephew takes her bank card and she doesn't get it back.",
        "Drank very little today, approx 300ml, urine dark.",
        "Meds given as per MAR, no missed doses.",
    ],
)
def test_clinical_content_not_redacted(clinical: str) -> None:
    assert redact(clinical).text == clinical


def test_spans_hold_no_original_values() -> None:
    out = redact("Mrs Sampleton rang on 07700 900123.")
    assert isinstance(out, RedactedText)
    assert {s.entity_type for s in out.spans} >= {"PERSON", "PHONE_NUMBER"}
    assert "Sampleton" not in repr(out.spans)


def _rates(notes: list[LabelledNote]) -> tuple[float, float]:
    pii_total = pii_hit = ev_total = ev_kept = 0
    for n in notes:
        text = redact(n.note.text).text
        pii_total += len(n.pii)
        pii_hit += sum(p not in text for p in n.pii)
        ev_total += len(n.gold.risk_flags)
        ev_kept += sum(f.evidence in text for f in n.gold.risk_flags)
    return pii_hit / pii_total, ev_kept / ev_total


@pytest.mark.parametrize("split", ["dev", "test"])
def test_dataset_pii_recall_and_evidence_preservation(split: str) -> None:
    """Regression floor. Measured 2026-11-06: dev 0.988/1.000, test 0.983/0.964."""
    recall, preserved = _rates(read_jsonl(DATA / f"{split}.jsonl"))
    assert recall >= 0.98
    assert preserved >= 0.95
