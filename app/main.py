"""FastAPI entry point."""

from fastapi import FastAPI

from app.api import audit, notes, review, schedule
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
for module in (notes, review, audit, schedule):
    app.include_router(module.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the process is up. Does not check dependencies."""
    return {"status": "ok", "environment": settings.environment}
