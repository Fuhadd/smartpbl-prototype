"""Domain schemas for care-note risk extraction.

`CareNote` is the pipeline input. `Extraction` is the contract the LLM must fill:
its JSON schema is passed to Ollama as a decoding constraint (Step 1.5), and the
same Pydantic model validates the response. One definition serves both, so they can't drift.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskCategory(StrEnum):
    FALLS = "falls"
    MEDICATION = "medication"
    NUTRITION_HYDRATION = "nutrition_hydration"
    SKIN_INTEGRITY = "skin_integrity"
    MOOD_BEHAVIOUR = "mood_behaviour"
    SAFEGUARDING = "safeguarding"
    MISSED_LATE_VISIT = "missed_late_visit"


class Severity(StrEnum):
    """Ordinal severity. Three levels keep LLM labels consistent and map to clear actions."""

    LOW = "low"  # note for the record; review at the routine care-plan review
    MEDIUM = "medium"  # coordinator follow-up within the day
    HIGH = "high"  # same-shift escalation; always routed to human review (Step 1.6)


class MedicationStatus(StrEnum):
    TAKEN = "taken"
    REFUSED = "refused"
    MISSED = "missed"
    PARTIAL = "partial"
    NOT_MENTIONED = "not_mentioned"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CareNote(_Strict):
    """A free-text note written by a carer after a visit. Refs are pseudonymous IDs, not names."""

    note_id: str = Field(min_length=1)
    client_ref: str = Field(min_length=1, description="Pseudonymous client ID, e.g. 'CL-0001'.")
    carer_ref: str = Field(min_length=1, description="Pseudonymous carer ID, e.g. 'CR-0001'.")
    visit_time: datetime
    text: str = Field(min_length=1, max_length=5000)


class RiskFlag(_Strict):
    """One risk the note gives evidence for. Evidence precedes severity/confidence."""

    category: RiskCategory
    evidence: str = Field(
        min_length=1,
        max_length=300,
        description="Exact verbatim quote from the note supporting this flag. Do not paraphrase.",
    )
    severity: Severity
    confidence: float = Field(
        ge=0.0, le=1.0, description="0.0-1.0; how clearly the note shows this risk."
    )


class Extraction(_Strict):
    """Structured output for one care note."""

    risk_flags: list[RiskFlag] = Field(
        description=(
            "Risks with evidence in the note. Omit risks the note negates, "
            "e.g. 'no signs of falls'."
        ),
    )
    medication_status: MedicationStatus
    follow_up_required: bool
    summary: str = Field(min_length=1, max_length=400, description="One or two neutral sentences.")


def extraction_json_schema() -> dict[str, Any]:
    """JSON schema for `Extraction`, as sent to the LLM as a decoding constraint."""
    return Extraction.model_json_schema()
