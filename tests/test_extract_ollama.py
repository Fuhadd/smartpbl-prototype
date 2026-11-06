"""Opt-in integration test against a real local Ollama: `uv run pytest -m ollama`.

Excluded from the default run (see pyproject addopts), so CI never needs a model.
"""

import httpx
import pytest

from app.core.config import get_settings
from app.nlp.extract import extract
from app.nlp.llm import OllamaClient
from app.nlp.prompts import load_prompt
from app.nlp.redact import redact
from app.nlp.schemas import RiskCategory

pytestmark = pytest.mark.ollama


@pytest.fixture(scope="module")
def client() -> OllamaClient:
    settings = get_settings()
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Ollama not reachable")
    return OllamaClient(settings.ollama_base_url, settings.llm_model, seed=settings.llm_seed)


def test_real_model_returns_valid_grounded_extraction(client: OllamaClient) -> None:
    note = redact("Mrs Sampleton was found on the floor by her bed and refused her tablets.")
    result = extract(note, client, load_prompt("extraction", "v2"))
    categories = {f.category for f in result.extraction.risk_flags}
    assert RiskCategory.FALLS in categories
    assert result.model_digest.startswith(client.model_digest[:6])
    assert "Sampleton" not in result.extraction.summary
