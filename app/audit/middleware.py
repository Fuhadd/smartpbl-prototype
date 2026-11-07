"""Audit middleware: one `api_request` row for every routed API call.

Pure ASGI, not Starlette's BaseHTTPMiddleware, because it must hold the response back:
for reads it buffers the response, writes the audit row, and only then sends it.
If the write fails, the client gets a 500 and the data never leaves the server (fail
closed). Writes have already committed their own domain events in the same transaction
as the change, so for them a failed access row is logged and the real response is sent:
answering 500 for a change that did happen would invite a duplicate retry.
"""

import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.audit import context
from app.audit.log import record
from app.audit.models import EventType, SubjectType
from app.core.db import get_session

log = logging.getLogger(__name__)

# Which path parameter names which kind of subject. A test fails if a route introduces a
# path parameter missing from this table, so no endpoint escapes subject tagging.
SUBJECT_PARAMS: dict[str, SubjectType] = {
    "note_id": SubjectType.CARE_NOTE,
    "flag_id": SubjectType.RISK_FLAG,
    "run_id": SubjectType.SCHEDULE_RUN,
    "carer_ref": SubjectType.CARER,
    "visit_id": SubjectType.VISIT,
}
UNAUDITED_PATHS = frozenset({"/health"})  # liveness probes would drown the log
READ_METHODS = frozenset({"GET", "HEAD"})
_FAIL_CLOSED_BODY = b'{"detail":"audit log unavailable; response withheld"}'


class AuditMiddleware:
    def __init__(self, app: ASGIApp, session_factory: Callable[[], Any]) -> None:
        self.app = app
        # A generator dependency, so tests' `dependency_overrides[get_session]` applies here
        # too (resolved per request: the override can change between tests).
        self.session_factory = session_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ctx = context.RequestAudit()
        context.bind(ctx)
        started = time.perf_counter()
        messages: list[Message] = []

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", str(ctx.request_id).encode()))
                message = {**message, "headers": headers}
            messages.append(message)

        await self.app(scope, receive, capture)

        route = scope.get("route")
        if not isinstance(route, APIRoute) or route.path in UNAUDITED_PATHS:
            await _replay(messages, send)
            return
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        entry = _entry(scope, route, status, ctx, time.perf_counter() - started)
        try:
            await run_in_threadpool(self._write, entry)
        except Exception:
            log.exception("audit write failed for %s %s", scope["method"], route.path)
            if scope["method"] in READ_METHODS:
                await _fail_closed(send, ctx)
                return
        await _replay(messages, send)

    def _write(self, entry: dict[str, Any]) -> None:
        provided = self.session_factory()
        # The real dependency is a generator; a test override may return a Session.
        session = provided if isinstance(provided, Session) else next(provided)
        try:
            record(session, EventType.API_REQUEST, **entry)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if not isinstance(provided, Session):
                provided.close()


def _entry(
    scope: Scope, route: APIRoute, status: int, ctx: context.RequestAudit, seconds: float
) -> dict[str, Any]:
    params: dict[str, Any] = scope.get("path_params", {})
    subject = next(
        ((SUBJECT_PARAMS[k], str(v)) for k, v in params.items() if k in SUBJECT_PARAMS), None
    )
    return {
        "actor": ctx.actor or "anonymous",
        "subject": subject,
        # Failed and successful logins: an HMAC of the username typed, never the raw text
        # (people sometimes type a password into the username box).
        "input_text": ctx.attempted_username,
        "output": {
            "method": scope["method"],
            "route": route.path,  # the template, not the raw path: no ids or query strings
            "status": status,
            "duration_ms": round(seconds * 1000, 1),
        },
    }


async def _replay(messages: list[Message], send: Send) -> None:
    for message in messages:
        await send(message)


async def _fail_closed(send: Send, ctx: context.RequestAudit) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-request-id", str(ctx.request_id).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _FAIL_CLOSED_BODY})


def session_factory_for(app: Any) -> Callable[[], Iterator[Session] | Session]:
    """The DB session generator the app's routes use, including test overrides."""
    return lambda: app.dependency_overrides.get(get_session, get_session)()
