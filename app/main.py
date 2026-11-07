"""FastAPI entry point."""

from fastapi import FastAPI

from app.api import audit, auth, notes, review, schedule, workforce
from app.audit.middleware import AuditMiddleware, session_factory_for
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(AuditMiddleware, session_factory=session_factory_for(app))
ROUTERS = tuple(m.router for m in (auth, notes, review, schedule, audit, workforce))
for router in ROUTERS:
    app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the process is up. Does not check dependencies."""
    return {"status": "ok", "environment": settings.environment}
