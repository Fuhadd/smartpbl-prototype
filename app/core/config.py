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
    # Tier 2 travel times: cached OSRM matrices are used when present; OSRM is queried only
    # if osrm_base_url is set; otherwise the calibrated haversine fallback.
    travel_cache_dir: str = "data/scheduling/travel"
    osrm_base_url: str | None = None
    osrm_data_version: str | None = None  # first 12 chars of the extract's MD5
    # Tier 4 auth. HS256 key: at least 32 bytes (RFC 7518 s3.2). The dev default is public;
    # refusing to start with it outside local development is Step 4.3 (secrets management).
    jwt_secret: SecretStr = SecretStr("dev-only-jwt-secret-not-for-real-use-0123456789")
    jwt_issuer: str = "smartpbl-api"
    jwt_audience: str = "smartpbl-clients"
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 7 * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
