"""Shared FastAPI dependencies. Tests swap these with `app.dependency_overrides`."""

from functools import lru_cache
from typing import Annotated

from fastapi import Header

from app.core.config import get_settings
from app.nlp.llm import ChatClient, OllamaClient
from app.nlp.prompts import PromptTemplate, load_prompt


@lru_cache
def get_llm_client() -> ChatClient:
    s = get_settings()
    return OllamaClient(s.ollama_base_url, s.llm_model, timeout_s=s.llm_timeout_s, seed=s.llm_seed)


def get_prompt() -> PromptTemplate:
    return load_prompt("extraction", get_settings().extraction_prompt_version)


def get_reviewer(
    x_reviewer: Annotated[str, Header(pattern=r"^[A-Za-z0-9_.-]{1,50}$")],
) -> str:
    """PROTOTYPE ONLY: the reviewer's identity is whatever the client claims. Replaced by
    the authenticated user from a JWT in Step 4.1; until then this is not access control."""
    return x_reviewer
