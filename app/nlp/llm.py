"""Minimal Ollama chat client over HTTP.

Uses httpx directly (not the ollama SDK): every request field is visible, and the
`ChatClient` protocol is easy to fake in tests.
"""

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Protocol

import httpx


class LLMTimeoutError(Exception):
    """The model did not answer within the configured timeout."""


@dataclass(frozen=True)
class ChatResponse:
    content: str
    model: str
    prompt_tokens: int
    output_tokens: int


class ChatClient(Protocol):
    model: str

    @property
    def model_digest(self) -> str: ...

    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> ChatResponse: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 60.0,
        seed: int = 42,
        num_ctx: int = 4096,
        keep_alive: str = "10m",
    ) -> None:
        self.model = model
        self._options = {"temperature": 0, "seed": seed, "num_ctx": num_ctx}
        self._keep_alive = keep_alive
        # connect fails fast; read covers model load plus generation.
        self._http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(timeout_s, connect=5.0))

    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> ChatResponse:
        body = {
            "model": self.model,
            "messages": messages,
            "format": schema,  # schema-constrained decoding
            "stream": False,
            "options": self._options,
            "keep_alive": self._keep_alive,
        }
        try:
            r = self._http.post("/api/chat", json=body)
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        r.raise_for_status()
        data = r.json()
        return ChatResponse(
            content=data["message"]["content"],
            model=data["model"],
            prompt_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    @cached_property
    def model_digest(self) -> str:
        """Hash of the exact weights for the audit trail (a tag like 'llama3.1:8b' can move)."""
        models = self._http.get("/api/tags").raise_for_status().json()["models"]
        return next(m["digest"] for m in models if m["name"] == self.model)
