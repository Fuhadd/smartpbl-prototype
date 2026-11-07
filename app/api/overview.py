"""GET /overview: the coordinator's day at a glance (Main.dc.html), in one request.

Each panel reads the same tables its own screen does, so the numbers agree with what the
coordinator sees when they click through. Sections the caller's role can't read are
returned as null rather than refused, and the two disclosures (note evidence, a carer's
risk) are audited exactly as the review queue and workforce list audit theirs.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_workforce, require
from app.api.review import queue_items
from app.api.workforce import MIN_SUPPORT_LOG_ODDS
from app.audit.log import record
from app.audit.models import EventType, SubjectType
from app.auth.models import User
from app.auth.permissions import Permission, has_permission
from app.core.db import get_session
from app.matching.models import ScheduleRun
from app.matching.presets import Preset, preset_for
from app.nlp.ground import GroundingStatus
from app.nlp.models import ExtractionRecord, ExtractionSource, ExtractionStatus, ReviewStatus
from app.nlp.models import RiskFlagRecord as Flag
from app.nlp.schemas import RiskCategory, Severity
from app.workforce.service import MODEL_NAME, WorkforceRisk

router = APIRouter(prefix="/overview", tags=["overview"], dependencies=[Depends(get_current_user)])
WINDOW_DAYS = 7  # "Last 7 days" on the category and pipeline panels
ATTENTION_NOTES = 4  # note rows in "Needs attention" (plus one schedule, one workforce row)


class AttentionNote(BaseModel):
    note_id: UUID
    client_ref: str
    visit_time: datetime
    severity: Severity  # the note's queue priority
    category: RiskCategory | None  # its top pending flag; None if only the extraction failed
    evidence: str | None


class ReviewSummary(BaseModel):
    awaiting_flags: int
    awaiting_high: int
    notes_waiting: int
    attention: list[AttentionNote]


class CategoryCount(BaseModel):
    category: RiskCategory
    count: int


class FlagsByCategory(BaseModel):
    window_days: int
    counts: list[CategoryCount]  # largest first; categories with no flags are left out


class PipelineHealth(BaseModel):
    window_days: int
    extractions: int
    schema_valid_rate: float | None  # share of LLM extractions that validated (None: no data)
    grounded_rate: float | None  # share of LLM flags whose evidence was found in the note
    median_latency_ms: float | None
    model_name: str | None  # the most recent successful extraction's model


class Baseline(BaseModel):
    solver: str
    travel_h: float
    familiar_pct: float


class UnassignedVisit(BaseModel):
    visit_id: str
    client_ref: str
    detail: str


class ScheduleSummary(BaseModel):
    run_id: UUID
    created_at: datetime
    scenario_name: str
    preset: Preset
    visits: int
    served: int
    unassigned: int
    carers_on_shift: int
    travel_h: float
    familiar_pct: float
    baseline: Baseline | None  # runs saved before Step 5.2b have no comparison
    first_unassigned: UnassignedVisit | None


class CheckIn(BaseModel):
    carer_ref: str
    factor_label: str
    factor_value: str


class WorkforceSummary(BaseModel):
    elevated: int
    total: int
    check_in: CheckIn | None


class OverviewOut(BaseModel):
    generated_at: datetime
    review: ReviewSummary
    flags_by_category: FlagsByCategory
    pipeline: PipelineHealth
    schedule: ScheduleSummary | None  # None: no rota saved yet, or role can't read schedules
    workforce: WorkforceSummary | None


def _review(session: Session) -> ReviewSummary:
    items = queue_items(session)
    pending = [f for q in items for f in q.pending_flags]
    return ReviewSummary(
        awaiting_flags=len(pending),
        awaiting_high=sum(f.severity is Severity.HIGH for f in pending),
        notes_waiting=len(items),
        attention=[
            AttentionNote(
                note_id=q.note_id,
                client_ref=q.client_ref,
                visit_time=q.visit_time,
                severity=q.priority,
                category=q.pending_flags[0].category if q.pending_flags else None,
                evidence=q.pending_flags[0].evidence if q.pending_flags else None,
            )
            for q in items[:ATTENTION_NOTES]
        ],
    )


def _flags_by_category(session: Session, since: datetime) -> FlagsByCategory:
    """Flags raised in the window, excluding those a reviewer rejected as wrong."""
    rows = session.execute(
        select(Flag.category, func.count())
        .where(Flag.created_at >= since, Flag.review_status != ReviewStatus.REJECTED)
        .group_by(Flag.category)
    ).all()
    counts = sorted((CategoryCount(category=c, count=n) for c, n in rows), key=lambda x: -x.count)
    return FlagsByCategory(window_days=WINDOW_DAYS, counts=counts)


def _pipeline(session: Session, since: datetime) -> PipelineHealth:
    llm = (ExtractionRecord.source == ExtractionSource.LLM, ExtractionRecord.created_at >= since)
    total, ok, median = session.execute(
        select(
            func.count(),
            func.count().filter(ExtractionRecord.status == ExtractionStatus.OK),
            func.percentile_cont(0.5).within_group(ExtractionRecord.latency_ms),
        ).where(*llm)
    ).one()
    flags, grounded = session.execute(
        select(
            func.count(),
            func.count().filter(Flag.grounding_status != GroundingStatus.UNGROUNDED),
        ).where(Flag.source == ExtractionSource.LLM, Flag.created_at >= since)
    ).one()
    model = session.scalar(
        select(ExtractionRecord.model_name)
        .where(*llm, ExtractionRecord.status == ExtractionStatus.OK)
        .order_by(ExtractionRecord.created_at.desc())
        .limit(1)
    )
    return PipelineHealth(
        window_days=WINDOW_DAYS,
        extractions=total,
        schema_valid_rate=round(ok / total, 4) if total else None,
        grounded_rate=round(grounded / flags, 4) if flags else None,
        median_latency_ms=round(median, 1) if median is not None else None,
        model_name=model,
    )


def _schedule(session: Session) -> ScheduleSummary | None:
    """The most recently saved rota. The prototype plans one synthetic day, so "today's
    schedule" is the latest run rather than a run dated today."""
    run = session.scalars(select(ScheduleRun).order_by(ScheduleRun.created_at.desc())).first()
    if run is None:
        return None
    m = run.metrics
    base = m.get("baseline")
    first = run.dropped[0] if run.dropped else None
    carers = m.get("carers_used", len({a.carer_ref for a in run.assignments}))
    return ScheduleSummary(
        run_id=run.id,
        created_at=run.created_at,
        scenario_name=run.scenario_name,
        preset=preset_for(run.params.get("continuity_weight_min", -1)),
        visits=m["visits"],
        served=m["served"],
        unassigned=m["dropped"],
        carers_on_shift=carers,
        travel_h=round(run.travel_s / 3600, 1),
        familiar_pct=m["familiar_pct"],
        baseline=Baseline(
            solver=base["solver"],
            travel_h=round(base["travel_s"] / 3600, 1),
            familiar_pct=base["familiar_pct"],
        )
        if base
        else None,
        first_unassigned=UnassignedVisit(
            visit_id=first["visit_id"], client_ref=first["client_ref"], detail=first["detail"]
        )
        if first
        else None,
    )


def _workforce(session: Session, viewer: User, w: WorkforceRisk) -> WorkforceSummary:
    """How many carers are in the support-priority group, and the first of them with a
    provider-side factor worth a supportive check-in. Naming that carer is a disclosure
    of employee profiling, so it is audited like the risk list."""
    ranked = w.ranked()
    check_in = None
    for c in ranked:
        if not c.support_priority:
            break
        lever = next(
            (r for r in c.explanation.reasons if r.lever and r.log_odds >= MIN_SUPPORT_LOG_ODDS),
            None,
        )
        if lever:
            check_in = CheckIn(
                carer_ref=c.carer_ref, factor_label=lever.label, factor_value=lever.value
            )
            break
    shown = [check_in.carer_ref] if check_in else []
    record(
        session,
        EventType.WORKFORCE_RISK_VIEWED,
        actor=f"user:{viewer.username}",
        model_name=MODEL_NAME,
        model_version=w.version,
        subject=(SubjectType.CARER, shown[0]) if shown else None,
        output={"carer_refs": shown, "view": "overview"},
    )
    return WorkforceSummary(
        elevated=sum(c.support_priority for c in ranked), total=len(ranked), check_in=check_in
    )


@router.get("")
def overview(
    viewer: Annotated[User, Depends(require(Permission.REVIEW_QUEUE_READ))],
    session: Annotated[Session, Depends(get_session)],
    # Resolved after the permission check, so a refused caller never triggers model training.
    w: Annotated[WorkforceRisk, Depends(get_workforce)],
) -> OverviewOut:
    now = datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    review = _review(session)
    # The attention rows show evidence quoted from notes: record which notes, as the queue does.
    shown = [str(a.note_id) for a in review.attention]
    record(
        session,
        EventType.REVIEW_QUEUE_VIEWED,
        actor=f"user:{viewer.username}",
        output={"note_ids": shown, "view": "overview"},
    )
    can = lambda p: has_permission(viewer.role, p)  # noqa: E731
    out = OverviewOut(
        generated_at=now,
        review=review,
        flags_by_category=_flags_by_category(session, since),
        pipeline=_pipeline(session, since),
        schedule=_schedule(session) if can(Permission.SCHEDULE_READ) else None,
        workforce=_workforce(session, viewer, w) if can(Permission.WORKFORCE_READ) else None,
    )
    session.commit()
    return out
