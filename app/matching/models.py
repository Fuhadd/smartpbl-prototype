"""Persistence for solver runs and their assignments (Step 2.6).

Data minimisation: the scenario itself (with locations) is not stored, only its name, seed
and a keyed hash, so a run can be matched to its input without keeping a copy of where
clients live. Assignments keep references, times and the human-readable reasons.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin


class ScheduleRun(CreatedAtMixin, Base):
    __tablename__ = "schedule_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scenario_name: Mapped[str] = mapped_column(String(100))
    scenario_seed: Mapped[int | None]
    scenario_hash: Mapped[str] = mapped_column(String(64))  # HMAC-SHA256 of the input JSON
    solver: Mapped[str] = mapped_column(String(50))  # e.g. "ortools-9.15.6755"
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(60))
    objective: Mapped[int] = mapped_column(Integer)
    travel_s: Mapped[int] = mapped_column(Integer)
    wall_s: Mapped[float] = mapped_column(Float)
    matrix_backend: Mapped[str] = mapped_column(String(120))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dropped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # visit + reason + detail
    requested_by: Mapped[str] = mapped_column(String(100))

    assignments: Mapped[list["ScheduleAssignment"]] = relationship(
        back_populates="run", order_by="(ScheduleAssignment.carer_ref, ScheduleAssignment.sequence)"
    )


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("schedule_runs.id"), index=True)
    carer_ref: Mapped[str] = mapped_column(String(20))
    sequence: Mapped[int]
    visit_id: Mapped[str] = mapped_column(String(20))
    client_ref: Mapped[str] = mapped_column(String(20))
    start_s: Mapped[int]
    end_s: Mapped[int]
    travel_s: Mapped[int]
    familiarity: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list[str]] = mapped_column(JSONB)

    run: Mapped[ScheduleRun] = relationship(back_populates="assignments")
