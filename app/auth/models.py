"""User accounts and refresh-token state.

Refresh tokens are JWTs, but each one's `jti` is also stored here so it can be rotated,
revoked, and checked for reuse. The token string itself is never stored.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, string_enum


class Role(StrEnum):
    COORDINATOR = "coordinator"
    MANAGER = "manager"
    CARER = "carer"


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Immutable once created (no rename endpoint): it is the actor recorded in audit rows.
    username: Mapped[str] = mapped_column(String(50), unique=True)
    # How the UI greets and attributes the user ("Hannah K."). Not used for any decision.
    display_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(string_enum(Role, length=20))
    is_active: Mapped[bool] = mapped_column(default=True)


class RefreshToken(CreatedAtMixin, Base):
    """One row per issued refresh token. A `family` is one login session: every rotation
    stays in the family, and reuse of a rotated token revokes the whole family."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[UUID | None]
