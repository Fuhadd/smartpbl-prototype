"""Login, token issue, refresh-token rotation with reuse detection, logout.

Functions add to the session but never commit: the router owns the transaction.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit.log import record
from app.audit.models import EventType, SubjectType
from app.auth.models import RefreshToken, Role, User
from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)


class RefreshTokenReuseError(InvalidTokenError):
    """A rotated (already-used) refresh token was presented again: likely stolen.
    The whole family has been revoked; the caller must commit that before failing."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # access-token lifetime, seconds (OAuth2 token-response convention)
    refresh_expires_in: int


def create_user(session: Session, username: str, password: str, role: Role) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    """The user if the credentials are right and the account is active, else None.
    The same answer (None) for unknown user, wrong password and disabled account."""
    user = session.scalar(select(User).where(User.username == username))
    ok = verify_password(password, user.password_hash if user else None)
    return user if ok and user is not None and user.is_active else None


def _issue(session: Session, user: User, family_id: UUID) -> tuple[TokenPair, UUID]:
    s = get_settings()
    # The role is in the access token for clients (role-aware UI routes). The server
    # never authorises from it: it reloads the user's current role on every request.
    access, _, _ = encode_token(user.id, TokenType.ACCESS, extra={"role": user.role.value})
    refresh, jti, expires = encode_token(user.id, TokenType.REFRESH)
    session.add(RefreshToken(jti=jti, user_id=user.id, family_id=family_id, expires_at=expires))
    session.flush()
    return TokenPair(access, refresh, s.access_token_ttl_s, s.refresh_token_ttl_s), jti


def issue_tokens(session: Session, user: User) -> TokenPair:
    """A new access + refresh pair at login: the start of a new token family."""
    return _issue(session, user, family_id=uuid4())[0]


def _revoke_family(session: Session, family_id: UUID, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def _load_refresh(session: Session, token: str) -> RefreshToken:
    claims = decode_token(token, TokenType.REFRESH)
    # Row lock: two concurrent refreshes of one token serialise, so only one can win.
    row = session.get(RefreshToken, UUID(claims["jti"]), with_for_update=True)
    if row is None or str(row.user_id) != claims["sub"]:
        raise InvalidTokenError("unknown refresh token")
    return row


def rotate(session: Session, token: str) -> tuple[TokenPair, User]:
    """Exchange a refresh token for a new pair; the old one is revoked (single use)."""
    row = _load_refresh(session, token)
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        _revoke_family(session, row.family_id, now)
        # A security signal for whoever reviews the log; committed with the revocation.
        record(
            session,
            EventType.REFRESH_TOKEN_REUSE_DETECTED,
            actor="system:auth",
            subject=(SubjectType.USER, str(row.user_id)),
            output={"family_id": str(row.family_id), "reused_jti": str(row.jti)},
        )
        raise RefreshTokenReuseError("refresh token reused")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        _revoke_family(session, row.family_id, now)
        raise InvalidTokenError("account disabled")
    row.revoked_at = now
    pair, row.replaced_by = _issue(session, user, family_id=row.family_id)
    return pair, user


def logout(session: Session, token: str) -> User:
    """End the session: revoke every refresh token in its family. Access tokens already
    issued stay valid until they expire (at most `access_token_ttl_s`)."""
    row = _load_refresh(session, token)
    _revoke_family(session, row.family_id, datetime.now(UTC))
    return session.get_one(User, row.user_id)
