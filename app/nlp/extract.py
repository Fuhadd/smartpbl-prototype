"""LLM risk extraction: redacted note -> validated `Extraction`.

Flow: render the versioned prompt -> schema-constrained chat -> Pydantic validation.
On invalid output or a timeout: one retry (the validation error is fed back to the model).
A second failure raises `ExtractionFailedError`. The caller routes the note to human review;
a note is never silently dropped.
"""

import time
from dataclasses import dataclass

from pydantic import ValidationError

from app.nlp.llm import ChatClient, LLMTimeoutError
from app.nlp.prompts import PromptTemplate
from app.nlp.redact import RedactedText
from app.nlp.schemas import Extraction, Severity, extraction_json_schema

MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class ExtractionResult:
    extraction: Extraction
    model: str
    model_digest: str
    prompt_version: str
    prompt_sha256: str
    attempts: int
    latency_ms: float
    errors: tuple[str, ...]  # errors from failed attempts that preceded success
    overrides: tuple[str, ...]  # derived fields corrected after validation, for the audit trail


def enforce_derived_fields(extraction: Extraction) -> tuple[Extraction, tuple[str, ...]]:
    """Recompute fields that are pure functions of other fields; never trust the model's copy.

    follow_up_required := any flag with severity medium or high. On dev (prompt v2), 9/80
    LLM outputs contradicted their own severities.
    """
    derived = any(f.severity is not Severity.LOW for f in extraction.risk_flags)
    if extraction.follow_up_required == derived:
        return extraction, ()
    fixed = extraction.model_copy(update={"follow_up_required": derived})
    return fixed, (f"follow_up_required: {extraction.follow_up_required} -> {derived}",)


class ExtractionFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"extraction failed after {len(errors)} attempt(s): {errors[-1]}")
        self.errors = tuple(errors)


def _retry_message(error: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": "Your previous answer was invalid: "
        f"{error[:500]}\nReturn corrected JSON matching the schema.",
    }


def extract(note: RedactedText, client: ChatClient, prompt: PromptTemplate) -> ExtractionResult:
    if not isinstance(note, RedactedText):  # enforced at runtime too: no raw text to the LLM
        raise TypeError("extract() requires RedactedText; call app.nlp.redact.redact() first")

    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.render_user(note.text)},
    ]
    schema = extraction_json_schema()
    errors: list[str] = []
    start = time.perf_counter()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat(messages, schema)
        except LLMTimeoutError as e:
            errors.append(f"timeout: {e}")
            continue
        try:
            extraction = Extraction.model_validate_json(response.content)
        except ValidationError as e:
            errors.append(f"invalid: {e.errors(include_url=False)}")
            messages = [
                *messages,
                {"role": "assistant", "content": response.content},
                _retry_message(errors[-1]),
            ]
            continue
        extraction, overrides = enforce_derived_fields(extraction)
        return ExtractionResult(
            extraction=extraction,
            model=response.model,
            model_digest=client.model_digest,
            prompt_version=f"{prompt.name}/{prompt.version}",
            prompt_sha256=prompt.sha256,
            attempts=attempt,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            errors=tuple(errors),
            overrides=overrides,
        )
    raise ExtractionFailedError(errors)
