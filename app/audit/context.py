"""Per-request audit context, shared between the middleware and the code below it.

The middleware creates one `RequestAudit` per HTTP request and binds it to a context
variable *before* calling the app. Context variables are copied into the tasks and worker
threads that serve the request, so code below sees the same object. Downstream code
mutates its fields (it never rebinds the variable), so the middleware sees, after the
response, who the caller turned out to be.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class RequestAudit:
    request_id: UUID = field(default_factory=uuid4)
    actor: str | None = None  # set once the caller is authenticated: "user:<username>"
    attempted_username: str | None = None  # login only; stored as an HMAC, never raw


_current: ContextVar[RequestAudit | None] = ContextVar("request_audit", default=None)


def bind(ctx: RequestAudit) -> None:
    _current.set(ctx)


def current() -> RequestAudit | None:
    """The current request's context, or None outside a request (scripts, unit tests)."""
    return _current.get()


def set_actor(username: str) -> None:
    if (ctx := current()) is not None:
        ctx.actor = f"user:{username}"
