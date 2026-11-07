"""POST /schedule/solve and GET /schedule/{id}."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import limiter
from app.matching.data import Scenario, integrity_problems
from app.matching.models import ScheduleRun
from app.matching.service import run_schedule

router = APIRouter(prefix="/schedule", tags=["schedule"], dependencies=[Depends(get_current_user)])
SessionDep = Annotated[Session, Depends(get_session)]
SOLVES_BY_USER = limiter("solve_user", lambda: get_settings().solve_limit_per_user)
SAMPLE_SCENARIO = Path("data/scheduling/scenario.json")
# Size caps for caller-supplied scenarios (OWASP API4): solver memory and time grow with
# visits x carers. About 4x the sample day (17 carers, 40 clients, 106 visits).
MAX_CARERS, MAX_CLIENTS, MAX_VISITS, MAX_CARER_LIST = 60, 200, 400, 10


class SolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Scenario | None = None  # omitted: the committed synthetic sample day
    # Capped: each request blocks a worker for up to 2 x time_limit_s (two-phase).
    time_limit_s: float = Field(default=10.0, gt=0, le=30)
    continuity_weight_min: int = Field(default=15, ge=0, le=60)

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        s = self.scenario
        if s is None:
            return self
        if len(s.name) > 100:
            raise ValueError("scenario name longer than 100 characters")
        for what, n, cap in (("carers", len(s.carers), MAX_CARERS),
                             ("clients", len(s.clients), MAX_CLIENTS),
                             ("visits", len(s.visits), MAX_VISITS)):  # fmt: skip
            if n > cap:
                raise ValueError(f"at most {cap} {what} per request (got {n})")
        if any(len(c.preferred_carers) > MAX_CARER_LIST or len(c.recent_carers) > MAX_CARER_LIST
               for c in s.clients):  # fmt: skip
            raise ValueError(f"at most {MAX_CARER_LIST} preferred or recent carers per client")
        if not s.carers:  # zero vehicles crash OR-Tools natively: refuse up front
            raise ValueError("a scenario needs at least one carer")
        return self


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    carer_ref: str
    sequence: int
    visit_id: str
    client_ref: str
    start_s: int
    end_s: int
    travel_s: int
    familiarity: str
    reasons: list[str]


class CarerRoute(BaseModel):
    carer_ref: str
    visits: list[AssignmentOut]
    travel_min: float


class ScheduleOut(BaseModel):
    id: UUID
    created_at: datetime
    scenario_name: str
    scenario_seed: int | None
    scenario_hash: str
    solver: str
    params: dict[str, Any]
    status: str
    objective: int
    travel_min: float
    wall_s: float
    matrix_backend: str
    metrics: dict[str, Any]
    routes: list[CarerRoute]
    dropped: list[dict[str, Any]]
    requested_by: str


def _out(run: ScheduleRun) -> ScheduleOut:
    by_carer: dict[str, list[AssignmentOut]] = {}
    for a in sorted(run.assignments, key=lambda a: (a.carer_ref, a.sequence)):
        by_carer.setdefault(a.carer_ref, []).append(AssignmentOut.model_validate(a))
    return ScheduleOut(
        id=run.id,
        created_at=run.created_at,
        scenario_name=run.scenario_name,
        scenario_seed=run.scenario_seed,
        scenario_hash=run.scenario_hash,
        solver=run.solver,
        params=run.params,
        status=run.status,
        objective=run.objective,
        travel_min=round(run.travel_s / 60, 1),
        wall_s=run.wall_s,
        matrix_backend=run.matrix_backend,
        metrics=run.metrics,
        routes=[
            CarerRoute(carer_ref=c, visits=v, travel_min=round(sum(a.travel_s for a in v) / 60, 1))
            for c, v in by_carer.items()
        ],
        dropped=run.dropped,
        requested_by=run.requested_by,
    )


@router.post("/solve", status_code=status.HTTP_201_CREATED)
def solve_schedule(
    user: Annotated[User, Depends(require(Permission.SCHEDULE_SOLVE))],
    body: SolveRequest,
    session: SessionDep,
) -> ScheduleOut:
    """Plan one day: OR-Tools VRPTW (+ two-phase continuity if the weight is > 0), with
    reasons for every assignment and every unassigned visit. Synchronous (10-60 s)."""
    SOLVES_BY_USER.check(str(user.id))  # a solve holds a worker for up to a minute
    scenario = body.scenario or Scenario.model_validate_json(
        SAMPLE_SCENARIO.read_text(encoding="utf-8")
    )
    if problems := integrity_problems(scenario):  # unservable visits are reported, not 422
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"problems": problems[:20]})
    # No query has run yet, so no transaction is open during the solve (writes come after).
    run = run_schedule(
        session,
        scenario,
        time_limit_s=body.time_limit_s,
        continuity_weight_min=body.continuity_weight_min,
        requested_by=user.username,
    )
    session.commit()
    return _out(run)


@router.get("/{run_id}")
def get_schedule(
    _: Annotated[User, Depends(require(Permission.SCHEDULE_READ))],
    run_id: UUID,
    session: SessionDep,
) -> ScheduleOut:
    run = session.get(ScheduleRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule run not found")
    return _out(run)
