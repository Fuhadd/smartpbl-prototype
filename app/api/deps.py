"""Shared FastAPI dependencies. Tests swap these with `app.dependency_overrides`."""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.audit.context import set_actor
from app.auth.models import User
from app.auth.permissions import Permission, has_permission
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.nlp.llm import ChatClient, OllamaClient
from app.nlp.prompts import PromptTemplate, load_prompt
from app.workforce.service import WorkforceRisk, get_workforce_risk


@lru_cache
def get_llm_client() -> ChatClient:
    s = get_settings()
    return OllamaClient(s.ollama_base_url, s.llm_model, timeout_s=s.llm_timeout_s, seed=s.llm_seed)


def get_prompt() -> PromptTemplate:
    return load_prompt("extraction", get_settings().extraction_prompt_version)


# auto_error=False: a missing token gets our own 401 (with WWW-Authenticate), the same
# response as a bad one, rather than FastAPI's default message.
_bearer = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def unauthorized() -> HTTPException:
    """One response for every authentication failure: no hint which check failed."""
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """The active user behind a valid access token. Reloaded from the database on every
    request, so disabling an account or changing a role takes effect immediately."""
    if token is None:
        raise unauthorized()
    try:
        claims = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as e:
        raise unauthorized() from e
    user = session.get(User, UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise unauthorized()
    set_actor(user.username)  # the audit middleware records who made this request
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(permission: Permission) -> Callable[[User], User]:
    """Dependency factory: `Depends(require(Permission.REVIEW_DECIDE))`. 401 without a
    valid token, 403 with one whose role lacks the permission."""

    def check(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient permissions")
        return user

    check.required_permission = permission  # type: ignore[attr-defined]  (route guard test)
    return check


def get_workforce() -> WorkforceRisk:
    """The cached attrition model and its scored workforce (trained on first use)."""
    return get_workforce_risk()
