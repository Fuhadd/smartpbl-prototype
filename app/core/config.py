"""Application settings loaded from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SMARTPBL_", extra="ignore")

    app_name: str = "SMARTPBL Prototype"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://smartpbl:smartpbl@localhost:5432/smartpbl"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
