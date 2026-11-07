"""The audit screen's timeline: a read-only projection of the append-only log.

The log stores fine-grained rows (a single care note writes note_ingested, pii_redacted,
extraction_completed, baseline_completed and flags_routed, plus an api_request row). A
person auditing decisions wants one line per meaningful thing: "note submitted",
"AI output", "human decision", "schedule run", "access denied". This module groups the
rows into those entries without changing or copying them; every entry lists the ids of
the rows it was built from, so it can always be traced back to the raw log.

Pagination is keyset on each entry's *anchor* row (the first row of its group), so a
page boundary never splits a group, and new rows arriving between pages never shift it.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import ColumnElement, String, and_, cast, exists, false, or_, select
from sqlalchemy.orm import Session, aliased

from app.audit.models import AuditEvent, EventType, SubjectType
from app.auth.models import Role, User
from app.matching.models import ScheduleRun
from app.matching.presets import preset_for
from app.nlp.models import CareNoteRecord

DISPLAY_TZ = ZoneInfo("Europe/London")  # the provider's local time, for the detail lines
MAX_PAGE = 200


class EntryKind(StrEnum):
    NOTE_SUBMITTED = "note_submitted"
    AI_OUTPUT = "ai_output"
    HUMAN_DECISION = "human_decision"
    SCHEDULE_RUN = "schedule_run"
    ACCESS_DENIED = "access_denied"
    SECURITY_ALERT = "security_alert"


class EntryFilter(StrEnum):
    """The filter pills on Audit.dc.html."""

    ALL = "all"
    AI_OUTPUT = "ai_output"
    HUMAN_DECISION = "human_decision"
    SCHEDULE_RUN = "schedule_run"
    ACCESS = "access"


FILTER_KINDS: dict[EntryFilter, frozenset[EntryKind]] = {
    EntryFilter.ALL: frozenset(EntryKind),
    EntryFilter.AI_OUTPUT: frozenset({EntryKind.AI_OUTPUT}),
    EntryFilter.HUMAN_DECISION: frozenset({EntryKind.HUMAN_DECISION}),
    EntryFilter.SCHEDULE_RUN: frozenset({EntryKind.SCHEDULE_RUN}),
    EntryFilter.ACCESS: frozenset({EntryKind.ACCESS_DENIED, EntryKind.SECURITY_ALERT}),
}

ET = EventType
# The rows that start an entry, and the rows that complete it (same request and note).
ANCHOR_KIND: dict[EventType, EntryKind] = {
    ET.NOTE_INGESTED: EntryKind.NOTE_SUBMITTED,
    ET.EXTRACTION_COMPLETED: EntryKind.AI_OUTPUT,
    ET.EXTRACTION_FAILED: EntryKind.AI_OUTPUT,
    ET.REVIEW_DECISION: EntryKind.HUMAN_DECISION,  # the first decision of the request only
    ET.SCHEDULE_SOLVED: EntryKind.SCHEDULE_RUN,
    ET.API_REQUEST: EntryKind.ACCESS_DENIED,  # only those answered 403
    ET.REFRESH_TOKEN_REUSE_DETECTED: EntryKind.SECURITY_ALERT,
}
COMPANIONS: dict[EntryKind, frozenset[EventType]] = {
    EntryKind.NOTE_SUBMITTED: frozenset({ET.PII_REDACTED}),
    EntryKind.AI_OUTPUT: frozenset({ET.FLAGS_ROUTED}),
    EntryKind.HUMAN_DECISION: frozenset({ET.REVIEW_DECISION, ET.REVIEW_ESCALATED}),
}
# Not shown as entries: successful requests and "viewed" rows (data-access records, still
# in the log and in GET /audit/{note_id}) and the rules baseline (a comparison output).

ROUTE_LABEL = {
    "/overview": "Overview",
    "/review/queue": "Review queue",
    "/review/{flag_id}": "Flag decision",
    "/review/notes/{note_id}": "Note decision",
    "/notes": "Care-note submission",
    "/notes/{note_id}": "Care note",
    "/schedule/solve": "Schedule optimiser",
    "/schedule/{run_id}": "Saved rota",
    "/workforce/risk": "Workforce risk",
    "/workforce/{carer_ref}/explanation": "Carer risk explanation",
    "/audit": "Audit log",
    "/audit/summary": "Audit log",
    "/audit/export": "Audit export",
    "/audit/{note_id}": "Note audit trail",
}
ROLE_WORD = {Role.COORDINATOR: "coordinator", Role.MANAGER: "care manager", Role.CARER: "carer"}


# --- response models ------------------------------------------------------------------


class Actor(BaseModel):
    kind: Literal["system", "user", "anonymous"]
    name: str  # display name for people, "System" for the pipeline and solver
    role: Role | None


class Detail(BaseModel):
    """One tile of an expanded row: a label, a bold value and an optional second line."""

    label: str
    value: str
    secondary: str | None = None
    mono: bool = False


class AuditEntry(BaseModel):
    id: int  # the anchor row's id; also the pagination cursor
    event_ids: list[int]  # every raw row this entry was built from
    occurred_at: datetime
    kind: EntryKind
    actor: Actor
    subject: str
    note_id: UUID | None
    version: str | None
    result: str
    details: list[Detail]


class AuditPage(BaseModel):
    entries: list[AuditEntry]
    next_before: int | None  # pass as `before` for the next (older) page; None at the end


# --- query ----------------------------------------------------------------------------

E = AuditEvent


def _is_anchor() -> ColumnElement[bool]:
    earlier = aliased(AuditEvent)
    first_decision = and_(
        E.event_type == ET.REVIEW_DECISION,
        ~exists().where(
            earlier.event_type == ET.REVIEW_DECISION,
            earlier.request_id == E.request_id,
            earlier.note_id == E.note_id,
            earlier.id < E.id,
        ),
    )
    denied = and_(E.event_type == ET.API_REQUEST, E.output["status"].as_integer() == 403)
    simple = [t for t in ANCHOR_KIND if t not in (ET.REVIEW_DECISION, ET.API_REQUEST)]
    return or_(E.event_type.in_(simple), first_decision, denied)


def _kind_condition(kinds: frozenset[EntryKind]) -> ColumnElement[bool]:
    types = [t for t, k in ANCHOR_KIND.items() if k in kinds]
    return E.event_type.in_(types) if types else false()


def _search_condition(q: str) -> ColumnElement[bool]:
    """Client ref, note id, user (username or display name), run or carer id."""
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    note = aliased(CareNoteRecord)
    api = aliased(AuditEvent)
    named_users = select("user:" + User.username).where(User.display_name.ilike(like, escape="\\"))
    by_actor = or_(E.actor.ilike(like, escape="\\"), E.actor.in_(named_users))
    submitted_by = select(api.request_id).where(
        api.event_type == ET.API_REQUEST,
        or_(api.actor.ilike(like, escape="\\"), api.actor.in_(named_users)),
    )
    note_match = select(note.id).where(
        or_(note.client_ref.ilike(like, escape="\\"), note.external_id.ilike(like, escape="\\"))
    )
    return or_(
        by_actor,
        E.subject_id.ilike(like, escape="\\"),
        cast(E.note_id, String).ilike(like, escape="\\"),
        E.note_id.in_(note_match),
        E.request_id.in_(submitted_by),
    )


def timeline_page(
    session: Session,
    *,
    kinds: frozenset[EntryKind] = FILTER_KINDS[EntryFilter.ALL],
    q: str | None = None,
    before: int | None = None,
    limit: int = 50,
) -> AuditPage:
    """One page of entries, newest first."""
    limit = max(1, min(limit, MAX_PAGE))
    where = [_is_anchor(), _kind_condition(kinds)]
    if before is not None:
        where.append(E.id < before)
    if q and q.strip():
        where.append(_search_condition(q.strip()))
    anchors = list(
        session.scalars(select(E).where(*where).order_by(E.id.desc()).limit(limit + 1)).all()
    )
    more = len(anchors) > limit
    anchors = anchors[:limit]
    entries = _Builder(session, anchors).build()
    return AuditPage(entries=entries, next_before=anchors[-1].id if more and anchors else None)


# --- grouping and copy ------------------------------------------------------------------


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _clock(ts: datetime) -> str:
    return ts.astimezone(DISPLAY_TZ).strftime("%H:%M")


def fingerprint(alg: str | None, digest: str | None) -> str:
    """ "hmac-sha256:3f9a…c71e": enough to compare by eye, not the whole digest."""
    if not digest:
        return "—"
    return f"{alg or 'sha256'}:{digest[:4]}…{digest[-4:]}"


def _prompt(version: str | None) -> str | None:
    return f"prompt {version.split('/')[-1]}" if version else None


def _model_line(e: AuditEvent) -> str | None:
    parts = [p for p in (e.model_name, _prompt(e.prompt_version)) if p]
    return " · ".join(parts) or None


@dataclass
class _Group:
    anchor: AuditEvent
    kind: EntryKind
    rows: list[AuditEvent] = field(default_factory=list)  # companions, in id order

    def of(self, *types: EventType) -> list[AuditEvent]:
        return [r for r in (self.anchor, *self.rows) if r.event_type in types]


class _Builder:
    """Fetches everything a page of anchors needs in three queries, then writes the copy."""

    def __init__(self, session: Session, anchors: Sequence[AuditEvent]) -> None:
        self.session = session
        self.anchors = anchors
        req_ids = {a.request_id for a in anchors if a.request_id}
        note_ids = {a.note_id for a in anchors if a.note_id}
        related: list[AuditEvent] = []
        if req_ids or note_ids:
            wanted = set().union(*COMPANIONS.values()) | {ET.API_REQUEST}
            ai = {ET.EXTRACTION_COMPLETED, ET.EXTRACTION_FAILED, ET.FLAGS_ROUTED}
            related = list(
                session.scalars(
                    select(E)
                    .where(
                        or_(
                            and_(E.request_id.in_(req_ids), E.event_type.in_(wanted)),
                            and_(E.note_id.in_(note_ids), E.event_type.in_(wanted | ai)),
                        )
                    )
                    .order_by(E.id)
                ).all()
            )
        self.related = related
        self.requests = {r.request_id: r for r in related if r.event_type == ET.API_REQUEST}
        self.users = self._users([*anchors, *related])
        self.notes = self._notes(note_ids)
        self.runs = self._runs(anchors)

    def _users(self, rows: Iterable[AuditEvent]) -> dict[str, User]:
        names = {r.actor.removeprefix("user:") for r in rows if r.actor.startswith("user:")}
        if not names:
            return {}
        found = self.session.scalars(select(User).where(User.username.in_(names))).all()
        return {u.username: u for u in found}

    def _notes(self, ids: set[UUID]) -> dict[UUID, CareNoteRecord]:
        if not ids:
            return {}
        rows = self.session.scalars(select(CareNoteRecord).where(CareNoteRecord.id.in_(ids)))
        return {n.id: n for n in rows}

    def _runs(self, anchors: Sequence[AuditEvent]) -> dict[str, ScheduleRun]:
        ids = [
            UUID(a.subject_id)
            for a in anchors
            if a.event_type == ET.SCHEDULE_SOLVED and a.subject_id
        ]
        if not ids:
            return {}
        rows = self.session.scalars(select(ScheduleRun).where(ScheduleRun.id.in_(ids)))
        return {str(r.id): r for r in rows}

    def build(self) -> list[AuditEntry]:
        return [self._entry(self._group(a)) for a in self.anchors]

    def _group(self, anchor: AuditEvent) -> _Group:
        kind = ANCHOR_KIND[anchor.event_type]
        types = COMPANIONS.get(kind, frozenset())
        rows = [
            r
            for r in self.related
            if r.event_type in types
            and r.id > anchor.id
            and r.note_id == anchor.note_id
            and r.request_id == anchor.request_id
            and (anchor.request_id is not None or kind is not EntryKind.HUMAN_DECISION)
        ]
        return _Group(anchor, kind, rows)

    # --- actors and subjects

    def _actor(self, actor: str) -> Actor:
        if actor.startswith("user:"):
            username = actor.removeprefix("user:")
            user = self.users.get(username)
            name = (user.display_name or user.username) if user else username
            return Actor(kind="user", name=name, role=user.role if user else None)
        if actor == "anonymous":
            return Actor(kind="anonymous", name="Not signed in", role=None)
        return Actor(kind="system", name="System", role=None)

    def _note_subject(self, note_id: UUID | None) -> str:
        note = self.notes.get(note_id) if note_id else None
        return f"{note.client_ref} · care note" if note else "Deleted note"

    # --- entries

    def _entry(self, g: _Group) -> AuditEntry:
        a = g.anchor
        actor, subject, version, result, details = getattr(self, f"_{g.kind.value}")(g)
        return AuditEntry(
            id=a.id,
            event_ids=[r.id for r in (a, *g.rows)],
            occurred_at=a.occurred_at,
            kind=g.kind,
            actor=actor,
            subject=subject,
            note_id=a.note_id,
            version=version,
            result=result,
            details=details,
        )

    def _note_submitted(self, g: _Group) -> tuple:
        a = g.anchor
        submitter = self.requests.get(a.request_id) if a.request_id else None
        redacted = g.of(ET.PII_REDACTED)
        entities: dict[str, int] = redacted[0].output.get("entities", {}) if redacted else {}
        n = sum(entities.values())
        result = _plural(n, "identifier") + " redacted" if n else "No identifiers found"
        kinds = " · ".join(
            f"{k.replace('_', ' ').title()} {v}" for k, v in sorted(entities.items())
        )
        details = [
            Detail(
                label="Redaction",
                value=kinds or "Nothing to redact",
                secondary="Masked before any AI call",
            ),
            Detail(
                label="Input fingerprint",
                value=fingerprint(a.hash_alg, a.input_hash),
                secondary="Raw text not stored in the log",
                mono=True,
            ),
        ]
        actor = self._actor(submitter.actor if submitter else a.actor)
        return actor, self._note_subject(a.note_id), None, result, details

    def _ai_summary(self, extraction: AuditEvent, routed: AuditEvent | None) -> tuple[str, str]:
        """("3 flags · routed to review", "3 flags · 3 / 3 grounded")"""
        if extraction.event_type == ET.EXTRACTION_FAILED:
            return "Extraction failed · rules baseline used", "No AI flags · person reviews"
        flags: list[dict[str, Any]] = routed.output.get("flags", []) if routed else []
        llm = [f for f in flags if f.get("source") == "llm"]
        grounded = sum(f.get("grounding") != "ungrounded" for f in llm)
        routed_to = (
            "routed to review"
            if routed and routed.output.get("review_required")
            else ("auto-accepted")
        )
        n = len(flags)
        return f"{_plural(n, 'flag')} · {routed_to}", (
            f"{_plural(len(llm), 'flag')} · {grounded} / {len(llm)} grounded"
        )

    def _ai_output(self, g: _Group) -> tuple:
        a = g.anchor
        routed = next(iter(g.of(ET.FLAGS_ROUTED)), None)
        result, grounding = self._ai_summary(a, routed)
        reasons = sorted(
            {
                r
                for f in (routed.output.get("flags", []) if routed else [])
                for r in f.get("reasons", [])
            }
        )
        attempts = (a.output or {}).get("attempts")
        details = [
            Detail(
                label="Model",
                value=a.model_name or "—",
                secondary=f"weights {a.model_version[:12]}" if a.model_version else None,
            ),
            Detail(
                label="Prompt",
                value=a.prompt_version or "—",
                secondary=f"{_plural(attempts, 'attempt')}" if attempts else None,
            ),
            Detail(
                label="Grounding and routing",
                value=grounding,
                secondary=", ".join(r.replace("_", " ") for r in reasons) or None,
            ),
            Detail(
                label="Input fingerprint",
                value=fingerprint(a.hash_alg, a.input_hash),
                secondary="Redacted text; raw text not stored in the log",
                mono=True,
            ),
        ]
        actor = self._actor(a.actor)
        return actor, self._note_subject(a.note_id), _model_line(a), result, details

    def _linked_ai(self, g: _Group) -> tuple[AuditEvent | None, AuditEvent | None]:
        """The latest extraction (and its routing) for this note before the decision."""
        a = g.anchor
        earlier = [r for r in self.related if r.note_id == a.note_id and r.id < a.id]
        ext = next(
            (
                r
                for r in reversed(earlier)
                if r.event_type in (ET.EXTRACTION_COMPLETED, ET.EXTRACTION_FAILED)
            ),
            None,
        )
        routed = next((r for r in reversed(earlier) if r.event_type == ET.FLAGS_ROUTED), None)
        return ext, routed

    def _human_decision(self, g: _Group) -> tuple:
        a = g.anchor
        decisions = g.of(ET.REVIEW_DECISION)
        actions = Counter(d.output.get("action", "?") for d in decisions)
        escalation = next(iter(g.of(ET.REVIEW_ESCALATED)), None)
        ext, routed = self._linked_ai(g)
        flag_category = {
            f["flag_id"]: f.get("category", "")
            for f in (routed.output.get("flags", []) if routed else [])
        }

        if set(actions) == {"acknowledge"}:
            result, decided = "Acknowledged", "Acknowledged with no flags to decide"
        elif set(actions) == {"approve"}:
            result = "Approved"
            decided = f"Approved {_plural(actions['approve'], 'flag')} unchanged"
        else:
            order = ("approve", "edit", "reject")
            words = {"approve": "approved", "edit": "edited", "reject": "rejected"}
            result = ", ".join(f"{actions[k]} {words[k]}" for k in order if actions[k])
            result = result[:1].upper() + result[1:]
            decided = result
        if escalation:
            result += " · escalated"
        esc = (
            "Escalated to care manager ("
            + "; ".join(
                f"{f['category'].replace('_', ' ')}, {f['severity']}"
                for f in escalation.output.get("flags", [])
            )
            + ")"
            if escalation
            else "Not escalated"
        )

        changes = []
        for d in decisions:
            diff: dict[str, dict[str, Any]] = d.output.get("diff", {})
            fields = [
                f"{k} {v.get('before')} → {v.get('after')}"
                for k, v in diff.items()
                if k != "review_status"
            ]
            if fields:
                cat = flag_category.get(d.output.get("flag_id"), "").replace("_", " ")
                changes.append(f"{cat.capitalize() or 'Flag'}: {', '.join(fields)}")

        linked = Detail(label="Linked AI output", value="None found")
        fp = Detail(
            label="Input fingerprint",
            value="—",
            mono=True,
            secondary="Raw text not stored in the log",
        )
        if ext:
            _, grounding = self._ai_summary(ext, routed)
            line = " · ".join(p for p in (_clock(ext.occurred_at), _model_line(ext)) if p)
            linked = Detail(label="Linked AI output", value=line, secondary=grounding)
            fp.value = fingerprint(ext.hash_alg, ext.input_hash)
        details = [
            Detail(label="Decision", value=decided, secondary=esc),
            linked,
            fp,
            Detail(
                label="Reviewer changes",
                value="; ".join(changes) if changes else "None",
                secondary=None if changes else "Edits would show as a diff",
            ),
        ]
        return self._actor(a.actor), self._note_subject(a.note_id), None, result, details

    def _schedule_run(self, g: _Group) -> tuple:
        a = g.anchor
        out = a.output or {}
        params = out.get("params", {})
        preset = preset_for(params.get("continuity_weight_min", -1)).value
        seed = out.get("scenario_seed")
        version = " · ".join(
            p for p in ("OR-Tools", preset, f"seed {seed}" if seed is not None else None) if p
        )
        run = self.runs.get(a.subject_id or "")
        if run:
            result = f"{run.metrics['served']} / {run.metrics['visits']} assigned"
        else:
            result = f"{_plural(out.get('dropped', 0), 'visit')} unassigned"
        details = [
            Detail(
                label="Solver",
                value=f"OR-Tools {a.model_version or ''}".strip(),
                secondary=out.get("matrix_backend"),
            ),
            Detail(
                label="Parameters",
                value=f"{preset} · continuity {params.get('continuity_weight_min')} min",
                secondary=f"time limit {params.get('time_limit_s')} s",
            ),
            Detail(
                label="Objective", value=str(out.get("objective", "—")), secondary=out.get("status")
            ),
            Detail(
                label="Input fingerprint",
                value=fingerprint(a.hash_alg, a.input_hash),
                secondary="Scenario not stored, only its hash",
                mono=True,
            ),
        ]
        subject = f"Rota · {out.get('scenario_name', 'unknown scenario')}"
        return self._actor(a.actor), subject, version, result, details

    def _access_denied(self, g: _Group) -> tuple:
        a = g.anchor
        out = a.output or {}
        route = out.get("route", "")
        subject = ROUTE_LABEL.get(route, route)
        if a.subject_type is SubjectType.CARER and a.subject_id:
            subject += f" · {a.subject_id}"
        details = [
            Detail(
                label="Request",
                value=f"{out.get('method', '')} {route}".strip(),
                secondary=f"HTTP {out.get('status')} · {out.get('duration_ms')} ms",
                mono=True,
            ),
            Detail(
                label="Outcome",
                value="Refused before any data was read",
                secondary="Permission checked on the server",
            ),
        ]
        return self._actor(a.actor), subject, None, "Role lacks permission", details

    def _security_alert(self, g: _Group) -> tuple:
        a = g.anchor
        user = self.session.get(User, UUID(a.subject_id)) if a.subject_id else None
        subject = f"Session · {user.display_name or user.username}" if user else "Sign-in session"
        details = [
            Detail(
                label="What happened",
                value="A used refresh token was presented again",
                secondary="Likely token theft",
            ),
            Detail(
                label="Response",
                value="Every session in the family revoked",
                secondary=f"family {str((a.output or {}).get('family_id', ''))[:8]}",
            ),
        ]
        return self._actor(a.actor), subject, None, "Session revoked", details


def actor_label(actor: Actor) -> str:
    """ "Hannah K. · coordinator" (CSV export; the web client composes its own)."""
    return f"{actor.name} · {ROLE_WORD[actor.role]}" if actor.role else actor.name
