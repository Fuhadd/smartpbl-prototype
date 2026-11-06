"""Application settings loaded from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SMARTPBL_", extra="ignore")

    app_name: str = "SMARTPBL Prototype"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://smartpbl:smartpbl@localhost:5442/smartpbl"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    llm_timeout_s: float = 60.0
    llm_seed: int = 42
    extraction_prompt_version: str = "v2"
    # Key for HMAC input hashes in the audit log. The dev default is public; set a real
    # secret outside local development (Tier 4 secrets management).
    audit_hash_key: SecretStr = SecretStr("dev-only-not-secret")


@lru_cache
def get_settings() -> Settings:
    return Settings()
