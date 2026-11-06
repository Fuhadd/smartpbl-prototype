from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_read_prefixed_env(monkeypatch) -> None:
    monkeypatch.setenv("SMARTPBL_LLM_MODEL", "qwen2.5:3b")
    assert Settings().llm_model == "qwen2.5:3b"
