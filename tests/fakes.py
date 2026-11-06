"""Test doubles shared across test modules."""

from dataclasses import dataclass, field
from typing import Any

from app.nlp.llm import ChatResponse


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
