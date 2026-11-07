"""The carer app's reads: GET /me/visits and GET /me/visits/{visit_id} (Step 5.6).

Object-level authorisation (OWASP API1): every read starts from the signed-in user's own
`carer_ref`, so there is no carer id in the URL to tamper with. A visit that isn't on the
carer's rota is a 404, not a 403, so its existence isn't confirmed. Recent notes are only
shown for clients on today's rota (need to know), as redacted text, and each read is audited.
"""

from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require
from app.audit.log import record
from app.audit.models import EventType
from app.audit.timeline import DISPLAY_TZ
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session
from app.matching.rota import TASKS, CarerDay, RotaVisit, carer_day
from app.nlp.models import CareNoteRecord, ReviewStatus
from app.nlp.schemas import RiskCategory, Severity

router = APIRouter(prefix="/me", tags=["carer"], dependencies=[Depends(get_current_user)])
SessionDep = Annotated[Session, Depends(get_session)]
RECENT_NOTES = 3  # enough to see a trend; more would be reading the care record, not a handover


class Task(BaseModel):
    key: str
    label: str
    detail: str


class Place(BaseModel):
    lat: float
    lon: float


class SubmittedNote(BaseModel):
    note_id: str | None
    submitted_at: datetime
    urgent: bool


class MyVisit(BaseModel):
    visit_id: str
    sequence: int
    client_ref: str
    start_min: int  # planned arrival, minutes after midnight
    end_min: int
    duration_min: int
    travel_min: int  # driving from the previous stop (or the start)
    familiarity: str  # preferred / recent / new
    window_start_min: int | None  # the agreed arrival window, when known (sample day)
    window_end_min: int | None
    time_critical: bool
    tasks: list[Task]
    location: Place | None  # for directions; only the carer's own visits
    note: SubmittedNote | None  # this carer's note for this visit, if sent


class DaySummary(BaseModel):
    visits: int
    done: int
    travel_min: int


class MyDay(BaseModel):
    run_id: str
    day: date
    carer_ref: str
    summary: DaySummary
    visits: list[MyVisit]


class NoteFlag(BaseModel):
    category: RiskCategory
    severity: Severity


class RecentNote(BaseModel):
    note_id: str
    visit_time: datetime
    text: str  # redacted: names and addresses removed
    review_required: bool
    flags: list[NoteFlag]  # kept flags only (rejected ones are not shown)


class MyVisitDetail(MyVisit):
    recent_notes: list[RecentNote]


def _carer(user: Annotated[User, Depends(require(Permission.VISITS_READ_OWN))]) -> User:
    if user.carer_ref is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no carer profile is linked to this login")
    return user


CarerDep = Annotated[User, Depends(_carer)]


def _day(session: Session, user: User) -> CarerDay:
    day = carer_day(session, user.carer_ref or "")
    if day is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no rota saved yet")
    return day


def _submitted(session: Session, day: CarerDay, carer_ref: str) -> dict[str, CareNoteRecord]:
    """This carer's notes for visits in this run, written on the run's day.

    By local calendar day, not "after the run was saved": a timestamp comparison would mix
    the API's clock (run) with the database's transaction-start clock (notes).
    """
    local = day.run.created_at.astimezone(DISPLAY_TZ)
    day_start = datetime.combine(local.date(), time.min, tzinfo=DISPLAY_TZ)
    notes = session.scalars(
        select(CareNoteRecord)
        .where(CareNoteRecord.carer_ref == carer_ref)
        .where(CareNoteRecord.visit_id.in_([v.assignment.visit_id for v in day.visits]))
        .where(CareNoteRecord.created_at >= day_start)
        .order_by(CareNoteRecord.created_at)
    ).all()
    return {n.visit_id: n for n in notes if n.visit_id}  # latest wins


def _note(n: CareNoteRecord | None) -> SubmittedNote | None:
    if n is None:
        return None
    return SubmittedNote(note_id=n.external_id, submitted_at=n.created_at, urgent=n.urgent)


def _visit(v: RotaVisit, note: CareNoteRecord | None) -> MyVisit:
    a, spec = v.assignment, v.visit
    loc = v.scenario.client(a.client_ref).location if v.scenario else None
    return MyVisit(
        visit_id=a.visit_id,
        sequence=a.sequence,
        client_ref=a.client_ref,
        start_min=a.start_s // 60,
        end_min=a.end_s // 60,
        duration_min=(a.end_s - a.start_s) // 60,
        travel_min=round(a.travel_s / 60),
        familiarity=a.familiarity,
        window_start_min=spec.window_start if spec else None,
        window_end_min=spec.window_end if spec else None,
        time_critical=spec.time_critical if spec else False,
        tasks=[Task(key=s.value, label=TASKS[s][0], detail=TASKS[s][1]) for s in v.tasks],
        location=Place(lat=loc.lat, lon=loc.lon) if loc else None,
        note=_note(note),
    )


@router.get("/visits")
def my_visits(user: CarerDep, session: SessionDep) -> MyDay:
    """Today's visits for the signed-in carer, in order, with what's been written up."""
    day = _day(session, user)
    notes = _submitted(session, day, user.carer_ref or "")
    visits = [_visit(v, notes.get(v.assignment.visit_id)) for v in day.visits]
    return MyDay(
        run_id=str(day.run.id),
        day=day.run.created_at.astimezone(DISPLAY_TZ).date(),
        carer_ref=user.carer_ref or "",
        summary=DaySummary(
            visits=len(visits),
            done=sum(v.note is not None for v in visits),
            travel_min=sum(v.travel_min for v in visits),
        ),
        visits=visits,
    )


@router.get("/visits/{visit_id}")
def my_visit(
    visit_id: Annotated[str, Path(pattern=r"^V-\d{4}$")], user: CarerDep, session: SessionDep
) -> MyVisitDetail:
    """One visit on the carer's rota, with the client's most recent notes as a handover."""
    day = _day(session, user)
    v = day.find(visit_id)
    if v is None:  # not on this carer's rota: don't confirm whether it exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visit not on your rota")
    recent = session.scalars(
        select(CareNoteRecord)
        .where(CareNoteRecord.client_ref == v.assignment.client_ref)
        .order_by(CareNoteRecord.created_at.desc())
        .limit(RECENT_NOTES)
        .options(selectinload(CareNoteRecord.flags))
    ).all()
    # Reading notes about a client is a data access like the review queue: record which.
    record(session, EventType.CLIENT_NOTES_VIEWED, actor=f"user:{user.username}",
           output={"client_ref": v.assignment.client_ref, "visit_id": visit_id,
                   "note_ids": [str(n.id) for n in recent]})  # fmt: skip
    session.commit()
    note = _submitted(session, day, user.carer_ref or "").get(visit_id)
    return MyVisitDetail(
        **_visit(v, note).model_dump(),
        recent_notes=[
            RecentNote(
                note_id=str(n.id),
                visit_time=n.visit_time,
                text=n.redacted_text,
                review_required=n.review_required,
                flags=[
                    NoteFlag(category=f.category, severity=f.severity)
                    for f in n.flags
                    if f.review_status is not ReviewStatus.REJECTED
                ],
            )
            for n in recent
        ],
    )
