"""POST /auth/token, /auth/refresh, /auth/logout and GET /auth/me."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, unauthorized
from app.audit import context
from app.auth import service
from app.auth.models import Role
from app.auth.permissions import ROLE_PERMISSIONS, Permission
from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import limiter
from app.core.security import InvalidTokenError

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]
# Per IP: slows credential stuffing across many accounts. Per username: slows guessing
# one account from many IPs. Both checked before the (deliberately slow) Argon2 work.
LOGIN_BY_IP = limiter("login_ip", lambda: get_settings().login_limit_per_ip)
LOGIN_BY_USERNAME = limiter("login_username", lambda: get_settings().login_limit_per_username)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  (the OAuth2 token type name, not a secret)
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class MeOut(BaseModel):
    username: str
    display_name: str
    role: Role
    permissions: list[Permission]


def _out(pair: service.TokenPair) -> TokenOut:
    return TokenOut(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        refresh_token=pair.refresh_token,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post("/token")
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> TokenOut:
    """OAuth2 password flow (form-encoded `username`, `password`), so Swagger UI's
    Authorize button works. Same 401 for unknown user, wrong password, disabled account."""
    if (ctx := context.current()) is not None:
        ctx.attempted_username = form.username  # audited as an HMAC, success or failure
    # The socket peer. Behind a proxy, uvicorn's --proxy-headers with --forwarded-allow-ips
    # rewrites it from X-Forwarded-For; never trust that header from arbitrary clients.
    LOGIN_BY_IP.check(request.client.host if request.client else "unknown")
    LOGIN_BY_USERNAME.check(form.username.casefold())
    user = service.authenticate(session, form.username, form.password)
    if user is None:
        raise unauthorized()
    context.set_actor(user.username)
    pair = service.issue_tokens(session, user)
    session.commit()
    return _out(pair)


@router.post("/refresh")
def refresh(body: RefreshIn, session: SessionDep) -> TokenOut:
    """Single-use rotation: returns a new pair; the presented refresh token is revoked."""
    try:
        pair, user = service.rotate(session, body.refresh_token)
    except InvalidTokenError as e:
        # Commit before refusing: on reuse (or a disabled account) the service has revoked
        # the whole token family, and that must persist. For other failures it's a no-op.
        session.commit()
        raise unauthorized() from e
    session.commit()
    context.set_actor(user.username)
    return _out(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, session: SessionDep) -> None:
    try:
        user = service.logout(session, body.refresh_token)
    except InvalidTokenError as e:
        session.rollback()
        raise unauthorized() from e
    session.commit()
    context.set_actor(user.username)


@router.get("/me")
def me(user: CurrentUser) -> MeOut:
    """Who the token belongs to and what they may do, for role-aware clients."""
    perms = sorted(ROLE_PERMISSIONS[user.role])
    return MeOut(
        username=user.username, display_name=user.display_name, role=user.role, permissions=perms
    )
