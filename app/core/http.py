"""HTTP hardening middleware: request-size limit and security response headers.

Both are pure ASGI (see app/audit/middleware.py for why).
"""

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE = b'{"detail":"request body too large"}'


class BodySizeLimitMiddleware:
    """Reject bodies over `max_bytes` (OWASP API4: unrestricted resource consumption).

    A declared Content-Length over the limit is refused before reading anything. Bodies
    without one (chunked) are counted as they arrive; reading stops at the limit, and
    FastAPI turns the raised HTTPException into the 413 response.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            await send(
                {
                    "type": "http.response.start",
                    "status": status.HTTP_413_CONTENT_TOO_LARGE,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": _TOO_LARGE})
            return
        received = 0

        async def limited() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "request body too large")
            return message

        await self.app(scope, limited, send)


# OWASP REST Security cheat sheet headers for a JSON API. The CSP forbids everything,
# because a JSON response should never be rendered as a page, run scripts or be framed.
_API_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"cache-control", b"no-store"),  # health and HR data must not sit in shared caches
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
# Swagger UI and ReDoc are HTML pages that load scripts: no CSP for them (local only).
_DOC_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts  # only over HTTPS, so off for local development

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"].startswith(_DOC_PATHS)

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                extra = [
                    (k, v)
                    for k, v in _API_HEADERS
                    if k not in present and not (is_docs and k == b"content-security-policy")
                ]
                if self.hsts:
                    extra.append(_HSTS)
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, add_headers)


async def validation_error_without_input(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with where and why, but not the submitted values. FastAPI's default echoes each
    invalid field's `input`, which for a care note can be the note text (health data) and
    then lands in client logs and error trackers."""
    errors = [
        {k: v for k, v in err.items() if k not in ("input", "ctx", "url")} for err in exc.errors()
    ]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status.HTTP_422_UNPROCESSABLE_CONTENT)
