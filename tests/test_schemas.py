from datetime import datetime

import pytest
from pydantic import ValidationError

from app.nlp.schemas import (
    CareNote,
    Extraction,
    MedicationStatus,
    RiskCategory,
    Severity,
    extraction_json_schema,
)

VALID_EXTRACTION = {
    "risk_flags": [
        {
            "category": "falls",
            "evidence": "found on floor by bed",
            "severity": "high",
            "confidence": 0.9,
        }
    ],
    "medication_status": "taken",
    "follow_up_required": True,
    "summary": "Client found on floor; no injury seen. Meds taken.",
}


def test_valid_extraction_parses_into_enums() -> None:
    result = Extraction.model_validate(VALID_EXTRACTION)
    flag = result.risk_flags[0]
    assert flag.category is RiskCategory.FALLS
    assert flag.severity is Severity.HIGH
    assert result.medication_status is MedicationStatus.TAKEN


def test_no_flags_is_valid() -> None:
    payload = {**VALID_EXTRACTION, "risk_flags": [], "follow_up_required": False}
    assert Extraction.model_validate(payload).risk_flags == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "dehydration"),  # not in taxonomy
        ("severity", "critical"),  # not a defined level
        ("confidence", 1.5),  # out of range
        ("evidence", ""),  # empty evidence cannot be grounded
    ],
)
def test_invalid_flag_rejected(field: str, value: object) -> None:
    bad_flag = {**VALID_EXTRACTION["risk_flags"][0], field: value}
    with pytest.raises(ValidationError):
        Extraction.model_validate({**VALID_EXTRACTION, "risk_flags": [bad_flag]})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Extraction.model_validate({**VALID_EXTRACTION, "diagnosis": "UTI"})


def test_care_note_requires_text() -> None:
    with pytest.raises(ValidationError):
        CareNote(
            note_id="N-0001",
            client_ref="CL-0001",
            carer_ref="CR-0001",
            visit_time=datetime(2026, 1, 1, 9, 0),
            text="   ",  # stripped to empty
        )


def test_json_schema_is_constraining() -> None:
    schema = extraction_json_schema()
    assert schema["additionalProperties"] is False
    # Every field required: constrained decoding must emit risk_flags even when empty.
    assert set(schema["required"]) == set(Extraction.model_fields)
    flag = schema["$defs"]["RiskFlag"]
    assert list(flag["properties"])[:2] == ["category", "evidence"]
    assert set(schema["$defs"]["RiskCategory"]["enum"]) == {c.value for c in RiskCategory}
