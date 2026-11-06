"""Gold-labelled care-note records and JSONL persistence for the synthetic dataset."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.nlp.schemas import CareNote, MedicationStatus, RiskCategory, Severity


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoldFlag(_Frozen):
    category: RiskCategory
    severity: Severity
    evidence: str  # the exact sentence in the note that carries the risk


class GoldLabel(_Frozen):
    risk_flags: list[GoldFlag]
    medication_status: MedicationStatus
    follow_up_required: bool


class LabelledNote(_Frozen):
    note: CareNote
    gold: GoldLabel
    negated: list[RiskCategory]  # categories mentioned only as negations ("no falls")
    pii: list[str]  # synthetic identifiers inserted into the text (redaction targets)
    tags: list[str]  # difficulty/style tags, e.g. "hard", "multi", "noisy"


def write_jsonl(path: Path, records: list[LabelledNote]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8")


def read_jsonl(path: Path) -> list[LabelledNote]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [LabelledNote.model_validate_json(line) for line in lines if line.strip()]
