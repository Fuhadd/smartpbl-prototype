"""Domain model for one day of domiciliary-care scheduling (Tier 2).

Times are integer minutes from midnight on the scheduled day (420 = 07:00). One day, one
time zone, so no DST or date arithmetic is needed in the solver.

Prototype simplifications (see ADR-014): every carer drives; shifts are one continuous
window (no split shifts or breaks); no visit needs two carers ("double-up").
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

MINUTES_PER_DAY = 24 * 60


class Skill(StrEnum):
    PERSONAL_CARE = "personal_care"  # washing, dressing, toileting: every carer has it
    MEDICATION = "medication"  # trained to administer (not just prompt) medication
    MANUAL_HANDLING = "manual_handling"  # hoists and transfer aids
    DEMENTIA_CARE = "dementia_care"
    CATHETER_CARE = "catheter_care"


# Sets serialise in sorted order, so equal scenarios always produce identical JSON (and
# therefore identical audit hashes). Frozenset iteration order is not stable across runs.
SkillSet = Annotated[
    frozenset[Skill],
    PlainSerializer(lambda s: sorted(x.value for x in s), return_type=list[str]),
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Location(_Model):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Carer(_Model):
    carer_ref: str = Field(pattern=r"^CR-\d{4}$")
    skills: SkillSet
    shift_start: int = Field(ge=0, lt=MINUTES_PER_DAY)
    shift_end: int = Field(gt=0, le=MINUTES_PER_DAY)
    home: Location
    start: Location  # where the working day begins: home, or the office

    @model_validator(mode="after")
    def _check(self) -> "Carer":
        if self.shift_end <= self.shift_start:
            raise ValueError("shift_end must be after shift_start")
        if Skill.PERSONAL_CARE not in self.skills:
            raise ValueError("every carer has personal_care")
        return self


class Client(_Model):
    client_ref: str = Field(pattern=r"^CL-\d{4}$")
    location: Location
    needs: SkillSet
    preferred_carers: tuple[str, ...] = ()  # stated by the client or family
    recent_carers: tuple[str, ...] = ()  # visited in the last 28 days


class Visit(_Model):
    visit_id: str = Field(pattern=r"^V-\d{4}$")
    client_ref: str
    window_start: int = Field(ge=0, lt=MINUTES_PER_DAY)  # earliest arrival
    window_end: int = Field(gt=0, le=MINUTES_PER_DAY)  # latest arrival
    duration: int = Field(gt=0, le=240)  # minutes on site
    required_skills: SkillSet
    time_critical: bool = False  # e.g. Parkinson's medication: narrow window

    @model_validator(mode="after")
    def _check(self) -> "Visit":
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        return self


class Scenario(_Model):
    name: str
    seed: int
    carers: tuple[Carer, ...]
    clients: tuple[Client, ...]
    visits: tuple[Visit, ...]

    def client(self, ref: str) -> Client:
        return next(c for c in self.clients if c.client_ref == ref)


def qualified(carer: Carer, visit: Visit) -> bool:
    return visit.required_skills <= carer.skills


def can_serve(carer: Carer, visit: Visit) -> bool:
    """Skills match and the visit fits the shift if started at some point in its window
    (ignoring travel). A necessary, not sufficient, condition for an assignment."""
    latest_start = min(visit.window_end, carer.shift_end - visit.duration)
    return qualified(carer, visit) and max(visit.window_start, carer.shift_start) <= latest_start


def integrity_problems(s: Scenario) -> list[str]:
    """Malformed input: duplicates, unknown references, skills a client doesn't need.
    The API rejects these (422)."""
    problems: list[str] = []
    carers = {c.carer_ref for c in s.carers}
    clients = {c.client_ref: c for c in s.clients}
    for ref, n in _duplicates([c.carer_ref for c in s.carers]):
        problems.append(f"duplicate carer {ref} ({n}x)")
    for ref, n in _duplicates([v.visit_id for v in s.visits]):
        problems.append(f"duplicate visit {ref} ({n}x)")
    for c in s.clients:
        unknown = set(c.preferred_carers + c.recent_carers) - carers
        if unknown:
            problems.append(f"{c.client_ref}: unknown carers {sorted(unknown)}")
    for v in s.visits:
        client = clients.get(v.client_ref)
        if client is None:
            problems.append(f"{v.visit_id}: unknown client {v.client_ref}")
        elif not v.required_skills <= client.needs | {Skill.PERSONAL_CARE}:
            problems.append(f"{v.visit_id}: requires skills the client doesn't need")
    return problems


def unservable_visits(s: Scenario) -> list[str]:
    """Well-formed visits that no carer could ever do (skills or shift). The API still
    plans the rest and reports these; the synthetic generator rejects them."""
    return [
        f"{v.visit_id}: no carer has the skills and shift for it"
        for v in s.visits
        if not any(can_serve(c, v) for c in s.carers)
    ]


def validate_scenario(s: Scenario) -> list[str]:
    """Strict check (used by the generator): integrity problems plus unservable visits."""
    problems = integrity_problems(s)
    known = {c.client_ref for c in s.clients}
    servable = s.model_copy(update={"visits": tuple(v for v in s.visits if v.client_ref in known)})
    return problems + unservable_visits(servable)


def _duplicates(items: list[str]) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    for i in items:
        seen[i] = seen.get(i, 0) + 1
    return [(k, n) for k, n in seen.items() if n > 1]
