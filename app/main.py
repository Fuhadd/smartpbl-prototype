"""FastAPI entry point."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, me, notes, overview, review, schedule, workforce
from app.audit.middleware import AuditMiddleware, session_factory_for
from app.core.config import get_settings
from app.core.http import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    validation_error_without_input,
)

settings = get_settings()

# Interactive docs only for local development (OWASP API9: don't publish more surface
# than needed). The schema is still generated for the typed Tier 5 clients at build time.
docs = settings.is_local
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if docs else None,
    redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)
app.add_exception_handler(RequestValidationError, validation_error_without_input)
# add_middleware wraps the app, so the LAST added runs FIRST. Request order:
# CORS -> security headers -> body size limit -> audit -> routes.
app.add_middleware(AuditMiddleware, session_factory=session_factory_for(app))
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
app.add_middleware(SecurityHeadersMiddleware, hsts=not settings.is_local)
# Tokens travel in the Authorization header, not cookies: no credentials mode, so a
# malicious site can't make the browser send anything on the user's behalf.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=600,
)
ROUTERS = tuple(m.router for m in (auth, notes, review, schedule, audit, workforce, overview, me))
for router in ROUTERS:
    app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the process is up. Does not check dependencies."""
    return {"status": "ok", "environment": settings.environment}
