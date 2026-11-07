"""Application settings loaded from environment variables (or a local .env file)."""

from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Public development defaults. Accepted only when environment == "local" (see below).
DEV_AUDIT_HASH_KEY = "dev-only-not-secret"
DEV_JWT_SECRET = "dev-only-jwt-secret-not-for-real-use-0123456789"  # noqa: S105  (public dev default)
MIN_HS256_KEY_BYTES = 32  # RFC 7518 s3.2: key at least as long as the hash output


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
    # Key for HMAC input hashes in the audit log. The dev default is refused outside local.
    audit_hash_key: SecretStr = SecretStr(DEV_AUDIT_HASH_KEY)
    # Tier 2 travel times: cached OSRM matrices are used when present; OSRM is queried only
    # if osrm_base_url is set; otherwise the calibrated haversine fallback.
    travel_cache_dir: str = "data/scheduling/travel"
    osrm_base_url: str | None = None
    osrm_data_version: str | None = None  # first 12 chars of the extract's MD5
    # Tier 4 auth. HS256 key: at least 32 bytes. The dev default is public, so it is
    # refused outside local development (validator below).
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_issuer: str = "smartpbl-api"
    jwt_audience: str = "smartpbl-clients"
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 7 * 24 * 3600
    # Step 4.3. Browser origins allowed to call the API (React dashboard, Flutter web app).
    # Explicit list, never "*". Set as JSON: SMARTPBL_CORS_ORIGINS='["https://..."]'.
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8081"]
    max_body_bytes: int = 1_000_000  # largest legitimate body: a 400-visit scenario
    # Rate limits: requests per rolling 60 s. In-memory, per process (see ratelimit.py).
    login_limit_per_ip: int = 20
    login_limit_per_username: int = 5
    note_limit_per_user: int = 30  # each note costs an LLM call
    solve_limit_per_user: int = 3  # each solve holds a worker for up to a minute

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @model_validator(mode="after")
    def _refuse_insecure_outside_local(self) -> Self:
        if self.is_local:
            return self
        problems = []
        jwt_key = self.jwt_secret.get_secret_value()
        if jwt_key == DEV_JWT_SECRET:
            problems.append("SMARTPBL_JWT_SECRET is the public development default")
        if len(jwt_key.encode()) < MIN_HS256_KEY_BYTES:
            problems.append(f"SMARTPBL_JWT_SECRET is shorter than {MIN_HS256_KEY_BYTES} bytes")
        if self.audit_hash_key.get_secret_value() == DEV_AUDIT_HASH_KEY:
            problems.append("SMARTPBL_AUDIT_HASH_KEY is the public development default")
        if "*" in self.cors_origins:
            problems.append("SMARTPBL_CORS_ORIGINS must list origins, not '*'")
        if problems:
            raise ValueError(  # surfaces as a pydantic ValidationError at start-up
                f"refusing to start ({self.environment}): " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
