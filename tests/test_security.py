"""Password hashing and JWT verification: pure unit tests, no database."""

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)

SECRET = get_settings().jwt_secret.get_secret_value()


def _claims(**overrides) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    base = {
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "sub": str(uuid4()),
        "jti": str(uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return {k: v for k, v in {**base, **overrides}.items() if v is not None}


def test_password_hash_is_argon2id_salted_and_verifies() -> None:
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1.startswith("$argon2id$")
    assert h1 != h2  # random salt: equal passwords don't give equal hashes
    assert verify_password("correct horse", h1)
    assert not verify_password("wrong horse", h1)


def test_unknown_user_still_runs_a_verification() -> None:
    assert verify_password("anything", None) is False


def test_round_trip_and_extra_claims() -> None:
    sub = uuid4()
    token, jti, expires = encode_token(sub, TokenType.ACCESS, extra={"role": "manager"})
    claims = decode_token(token, TokenType.ACCESS)
    assert claims["sub"] == str(sub) and claims["jti"] == str(jti)
    assert claims["role"] == "manager"
    assert expires - datetime.now(UTC) <= timedelta(seconds=get_settings().access_token_ttl_s)


def test_token_type_is_enforced_both_ways() -> None:
    access, _, _ = encode_token(uuid4(), TokenType.ACCESS)
    refresh, _, _ = encode_token(uuid4(), TokenType.REFRESH)
    with pytest.raises(InvalidTokenError):
        decode_token(refresh, TokenType.ACCESS)
    with pytest.raises(InvalidTokenError):
        decode_token(access, TokenType.REFRESH)


def test_expired_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token, _, _ = encode_token(uuid4(), TokenType.ACCESS, now=past)
    with pytest.raises(InvalidTokenError, match="ExpiredSignature"):
        decode_token(token, TokenType.ACCESS)


def _forge(claims: dict, key: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_forge(_claims(), key="x" * 48), id="other-secret"),
        pytest.param(_forge(_claims(), algorithm="HS512"), id="other-algorithm-same-key"),
        pytest.param(_forge(_claims(aud="another-service")), id="wrong-audience"),
        pytest.param(_forge(_claims(iss="someone-else")), id="wrong-issuer"),
        pytest.param(_forge(_claims(jti=None)), id="missing-jti"),
        pytest.param(_forge(_claims(type=None)), id="missing-type"),
        pytest.param(_forge(_claims(sub="not-a-uuid")), id="malformed-sub"),
        pytest.param(jwt.encode(_claims(), None, algorithm="none"), id="alg-none"),
        pytest.param("not.a.jwt", id="garbage"),
    ],
)
def test_forged_or_malformed_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.ACCESS)


def test_tampered_payload_fails_signature() -> None:
    """Flip the role in the payload (as an attacker would) without re-signing."""
    token, _, _ = encode_token(uuid4(), TokenType.ACCESS, extra={"role": "carer"})
    header, payload, sig = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    data["role"] = "manager"
    forged = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    with pytest.raises(InvalidTokenError, match="InvalidSignature"):
        decode_token(f"{header}.{forged}.{sig}", TokenType.ACCESS)
