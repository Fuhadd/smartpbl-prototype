"""Human-readable reasons for every assignment and every unassigned visit (Step 2.6).

A coordinator must be able to see *why* the solver chose a carer before trusting it. The
reasons are recomputed from the scenario and the travel matrix, not taken from the solver,
so they describe facts that can be checked: skills, drive time, arrival vs window,
familiarity, and how many other carers could have done the visit.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.matching.continuity import Familiarity, familiarity
from app.matching.data import Scenario, Skill, Visit, can_serve
from app.matching.solver import Solution
from app.matching.travel import TravelMatrix


class DropReason(StrEnum):
    NO_ELIGIBLE_CARER = "no_eligible_carer"  # structural: skills/shift; no routing can fix it
    ELIGIBLE_CARERS_BUSY = "eligible_carers_busy"  # capacity: qualified carers fully booked


@dataclass(frozen=True)
class AssignmentExplanation:
    visit_id: str
    client_ref: str
    carer_ref: str
    sequence: int  # position in the carer's day, from 1
    start_s: int
    end_s: int
    travel_s: int
    travel_from: str  # "start" or the previous client_ref
    window_start: int  # minutes
    window_end: int
    skills_required: list[str]
    familiarity: Familiarity
    other_eligible: int  # eligible carers besides the one assigned
    reasons: list[str]


@dataclass(frozen=True)
class DropExplanation:
    visit_id: str
    client_ref: str
    reason: DropReason
    eligible_carers: list[str]
    time_critical: bool
    detail: str


def _hhmm(seconds_or_minutes: int, *, seconds: bool = True) -> str:
    m = seconds_or_minutes // 60 if seconds else seconds_or_minutes
    return f"{m // 60:02d}:{m % 60:02d}"


def _extra_skills(v: Visit) -> list[str]:
    return sorted(s.value for s in v.required_skills - {Skill.PERSONAL_CARE})


def explain(
    scenario: Scenario, matrix: TravelMatrix, solution: Solution
) -> tuple[list[AssignmentExplanation], list[DropExplanation]]:
    visits = {v.visit_id: v for v in scenario.visits}
    assigned: list[AssignmentExplanation] = []
    for route in solution.routes:
        prev = "start"
        for seq, stop in enumerate(route.stops, 1):
            v = visits[stop.visit_id]
            client = scenario.client(v.client_ref)
            fam = familiarity(client, route.carer_ref)
            eligible = [c.carer_ref for c in scenario.carers if can_serve(c, v)]
            extra = _extra_skills(v)
            reasons = [
                (
                    f"Has the required skills: {', '.join(extra)}"
                    if extra
                    else "Visit needs personal care only (every carer has it)"
                ),
                f"Drives {round(stop.travel_s / 60)} min from "
                + ("their start point" if prev == "start" else f"previous visit ({prev})"),
                f"Arrives {_hhmm(stop.start_s)}, within the {_hhmm(v.window_start, seconds=False)}"
                f"-{_hhmm(v.window_end, seconds=False)} window",
                {
                    Familiarity.PREFERRED: "Client's preferred carer",
                    Familiarity.RECENT: "Has visited this client recently",
                    Familiarity.NEW: "New to this client",
                }[fam],
                f"{len(eligible) - 1} other carer(s) were qualified and on shift",
            ]
            if v.time_critical:
                reasons.append("Time-critical medication: narrow window protected by the solver")
            assigned.append(
                AssignmentExplanation(
                    visit_id=v.visit_id,
                    client_ref=v.client_ref,
                    carer_ref=route.carer_ref,
                    sequence=seq,
                    start_s=stop.start_s,
                    end_s=stop.end_s,
                    travel_s=stop.travel_s,
                    travel_from=prev,
                    window_start=v.window_start,
                    window_end=v.window_end,
                    skills_required=extra,
                    familiarity=fam,
                    other_eligible=len(eligible) - 1,
                    reasons=reasons,
                )
            )
            prev = v.client_ref

    dropped = []
    for vid in solution.dropped:
        v = visits[vid]
        eligible = [c.carer_ref for c in scenario.carers if can_serve(c, v)]
        window = f"{_hhmm(v.window_start, seconds=False)}-{_hhmm(v.window_end, seconds=False)}"
        if not eligible:
            reason = DropReason.NO_ELIGIBLE_CARER
            detail = f"No carer on shift at {window} has: {', '.join(_extra_skills(v)) or '-'}"
        else:
            reason = DropReason.ELIGIBLE_CARERS_BUSY
            detail = (
                f"{len(eligible)} qualified carer(s) ({', '.join(eligible)}) were fully booked "
                f"for the {window} window"
            )
        dropped.append(
            DropExplanation(vid, v.client_ref, reason, eligible, v.time_critical, detail)
        )
    return assigned, dropped
