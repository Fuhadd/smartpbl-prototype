"""POST /auth/token, /auth/refresh, /auth/logout and GET /auth/me."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, unauthorized
from app.auth import service
from app.auth.models import Role
from app.auth.permissions import ROLE_PERMISSIONS, Permission
from app.core.db import get_session
from app.core.security import InvalidTokenError

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class MeOut(BaseModel):
    username: str
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
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> TokenOut:
    """OAuth2 password flow (form-encoded `username`, `password`), so Swagger UI's
    Authorize button works. Same 401 for unknown user, wrong password, disabled account."""
    user = service.authenticate(session, form.username, form.password)
    if user is None:
        raise unauthorized()
    pair = service.issue_tokens(session, user)
    session.commit()
    return _out(pair)


@router.post("/refresh")
def refresh(body: RefreshIn, session: SessionDep) -> TokenOut:
    """Single-use rotation: returns a new pair; the presented refresh token is revoked."""
    try:
        pair = service.rotate(session, body.refresh_token)
    except InvalidTokenError as e:
        # Commit before refusing: on reuse (or a disabled account) the service has revoked
        # the whole token family, and that must persist. For other failures it's a no-op.
        session.commit()
        raise unauthorized() from e
    session.commit()
    return _out(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, session: SessionDep) -> None:
    try:
        service.logout(session, body.refresh_token)
    except InvalidTokenError as e:
        session.rollback()
        raise unauthorized() from e
    session.commit()


@router.get("/me")
def me(user: CurrentUser) -> MeOut:
    """Who the token belongs to and what they may do, for role-aware clients."""
    perms = sorted(ROLE_PERMISSIONS[user.role])
    return MeOut(username=user.username, role=user.role, permissions=perms)
