"""LLM extraction tests with a fake client: no model is called."""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.nlp.extract import MAX_ATTEMPTS, ExtractionFailedError, extract
from app.nlp.llm import ChatResponse, LLMTimeoutError, OllamaClient
from app.nlp.prompts import NOTE_SLOT, load_prompt
from app.nlp.redact import RedactedText
from app.nlp.schemas import RiskCategory

VALID = json.dumps(
    {
        "risk_flags": [
            {
                "category": "falls",
                "evidence": "found on floor",
                "severity": "high",
                "confidence": 0.9,
            }
        ],
        "medication_status": "taken",
        "follow_up_required": True,
        "summary": "Client found on floor.",
    }
)
NOTE = RedactedText(text="<PERSON> found on floor by the bed.", spans=())


@dataclass
class FakeClient:
    """Returns scripted replies in order. A reply can be an exception to raise."""

    replies: list[str | Exception]
    model: str = "fake-model:1b"
    model_digest: str = "sha256-fake"
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    schemas: list[dict[str, Any]] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> ChatResponse:
        self.calls.append(messages)
        self.schemas.append(schema)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ChatResponse(content=reply, model=self.model, prompt_tokens=10, output_tokens=5)


@pytest.fixture
def prompt():
    return load_prompt("extraction", "v1")


def test_success_records_provenance(prompt) -> None:
    client = FakeClient([VALID])
    result = extract(NOTE, client, prompt)
    assert result.extraction.risk_flags[0].category is RiskCategory.FALLS
    assert result.attempts == 1
    assert result.model == "fake-model:1b"
    assert result.model_digest == "sha256-fake"
    assert result.prompt_version == "extraction/v1"
    assert result.prompt_sha256 == prompt.sha256
    assert result.errors == ()


def test_request_carries_system_prompt_note_and_schema(prompt) -> None:
    client = FakeClient([VALID])
    extract(NOTE, client, prompt)
    (messages,) = client.calls
    assert messages[0] == {"role": "system", "content": prompt.system}
    assert NOTE.text in messages[1]["content"]
    assert NOTE_SLOT not in messages[1]["content"]
    assert client.schemas[0]["title"] == "Extraction"


def test_invalid_then_valid_retries_with_error_feedback(prompt) -> None:
    client = FakeClient(['{"risk_flags": "oops"}', VALID])
    result = extract(NOTE, client, prompt)
    assert result.attempts == 2
    assert len(result.errors) == 1 and result.errors[0].startswith("invalid")
    retry = client.calls[1]
    assert retry[-2] == {"role": "assistant", "content": '{"risk_flags": "oops"}'}
    assert "previous answer was invalid" in retry[-1]["content"]


def test_two_failures_raise(prompt) -> None:
    client = FakeClient(["not json", "still not json"])
    with pytest.raises(ExtractionFailedError) as exc:
        extract(NOTE, client, prompt)
    assert len(exc.value.errors) == MAX_ATTEMPTS
    assert len(client.calls) == MAX_ATTEMPTS  # no third call


def test_timeout_is_retried_once(prompt) -> None:
    client = FakeClient([LLMTimeoutError("read timeout"), VALID])
    result = extract(NOTE, client, prompt)
    assert result.attempts == 2
    assert result.errors[0].startswith("timeout")


def test_raw_text_is_rejected_before_any_call(prompt) -> None:
    client = FakeClient([VALID])
    with pytest.raises(TypeError, match="RedactedText"):
        extract("Mrs Sampleton fell", client, prompt)  # type: ignore[arg-type]
    assert client.calls == []


def test_prompt_hash_changes_with_content(prompt, tmp_path, monkeypatch) -> None:
    import app.nlp.prompts as prompts_module

    folder = tmp_path / "extraction" / "v1"
    folder.mkdir(parents=True)
    (folder / "system.txt").write_text(prompt.system + " edited", encoding="utf-8")
    (folder / "user.txt").write_text(prompt.user, encoding="utf-8")
    monkeypatch.setattr(prompts_module, "PROMPTS_DIR", tmp_path)
    prompts_module.load_prompt.cache_clear()
    try:
        edited = prompts_module.load_prompt("extraction", "v1")
    finally:
        prompts_module.load_prompt.cache_clear()
    assert edited.version == prompt.version
    assert edited.sha256 != prompt.sha256  # same label, different content: detectable


def test_ollama_client_sends_deterministic_options() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "message": {"content": VALID}})

    client = OllamaClient("http://ollama.test", "m", seed=7)
    client._http = httpx.Client(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    client.chat([{"role": "user", "content": "x"}], {"type": "object"})
    assert seen["options"]["temperature"] == 0
    assert seen["options"]["seed"] == 7
    assert seen["format"] == {"type": "object"}
    assert seen["stream"] is False


def test_ollama_client_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = OllamaClient("http://ollama.test", "m")
    client._http = httpx.Client(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LLMTimeoutError):
        client.chat([], {})


def test_inconsistent_follow_up_is_overridden_and_recorded(prompt) -> None:
    inconsistent = json.loads(VALID) | {"follow_up_required": False}  # high flag, no follow-up
    result = extract(NOTE, FakeClient([json.dumps(inconsistent)]), prompt)
    assert result.extraction.follow_up_required is True
    assert result.overrides == ("follow_up_required: False -> True",)


def test_consistent_output_has_no_overrides(prompt) -> None:
    assert extract(NOTE, FakeClient([VALID]), prompt).overrides == ()


def test_all_prompt_versions_load_with_distinct_hashes() -> None:
    v1, v2 = load_prompt("extraction", "v1"), load_prompt("extraction", "v2")
    assert v1.sha256 != v2.sha256
    assert v1.user == v2.user  # v2 changed only the system prompt
