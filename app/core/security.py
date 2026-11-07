"""Password hashing (Argon2id) and JWT encoding/decoding (HS256, pinned).

Pure functions: no database. Token lifecycle (rotation, revocation) lives in
`app.auth.service`.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

ALGORITHM = "HS256"
# Every claim a SMARTPBL token must carry; PyJWT rejects a token missing any of them.
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "jti", "type"]

_hasher = PasswordHash.recommended()  # Argon2id with pwdlib's recommended parameters
# Verified against when the username doesn't exist, so a login takes about as long for an
# unknown user as for a wrong password (no username enumeration by timing).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """Any reason a token must not be accepted. Callers map it to 401, with no detail."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-work check: with no stored hash, still runs one Argon2 verification."""
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def encode_token(
    subject: UUID,
    token_type: TokenType,
    *,
    now: datetime | None = None,
    jti: UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, UUID, datetime]:
    """Sign a token; returns (token, jti, expires_at)."""
    s = get_settings()
    now = now or datetime.now(UTC)
    ttl = s.access_token_ttl_s if token_type is TokenType.ACCESS else s.refresh_token_ttl_s
    expires = now + timedelta(seconds=ttl)
    jti = jti or uuid4()
    claims = {
        **(extra or {}),
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "sub": str(subject),
        "jti": str(jti),
        "type": token_type.value,
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, jti, expires


def decode_token(token: str, expected: TokenType) -> dict[str, Any]:
    """Verify signature, algorithm, expiry, issuer, audience, required claims and type.

    `algorithms=[ALGORITHM]` is the critical line: the server decides the algorithm, never
    the token header (blocks `alg: none` and algorithm-confusion attacks).
    """
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=s.jwt_audience,
            issuer=s.jwt_issuer,
            options={"require": REQUIRED_CLAIMS},
        )
        for key in ("sub", "jti"):  # malformed ids make the token invalid, not a 500
            UUID(claims[key])
    except (jwt.InvalidTokenError, ValueError) as e:
        raise InvalidTokenError(type(e).__name__) from e
    if claims["type"] != expected.value:  # a refresh token is not an access token
        raise InvalidTokenError("wrong token type")
    return claims
