"""FastAPI entry point. Routers are added per module in later steps."""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the process is up. Does not check dependencies."""
    return {"status": "ok", "environment": settings.environment}
