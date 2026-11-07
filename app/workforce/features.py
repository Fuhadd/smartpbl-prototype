"""Per-carer working-day features derived from a Tier 2 schedule (Step 3.1).

A solved day says, for each carer: how long they drove, how long they waited between
visits, how many visits they made and how many were to clients who know them. These are
the working-conditions signals the attrition model will use, so they are computed from
real solver output rather than invented, and then aggregated per carer by the generator.

Definitions (minutes):
  paid      = visit time + driving between visits (the common "contact + travel" pay basis);
  gap       = waiting time between the first and last visit, i.e. unpaid idle time;
  split day = a single gap of SPLIT_GAP_MIN or more, which the carer experiences as a
              split shift even though the rota is one continuous window (ADR-014).
"""

from dataclasses import asdict, dataclass
from itertools import pairwise

from app.matching.continuity import Familiarity, familiarity
from app.matching.data import Scenario
from app.matching.solver import Route, Solution

SPLIT_GAP_MIN = 90  # e.g. 10:00 -> 11:30 doing nothing between the morning and lunch rounds


@dataclass(frozen=True)
class CarerDay:
    seed: int  # scenario the day came from
    carer_ref: str
    skills: int  # number of skills beyond personal care
    shift_min: int
    visits: int
    service_min: float
    drive_min: float
    gap_min: float
    longest_gap_min: float
    split_day: bool
    familiar_share: float | None  # None on a day with no visits

    @property
    def paid_min(self) -> float:
        return self.service_min + self.drive_min

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _gaps_min(route: Route) -> list[float]:
    """Idle minutes between consecutive visits: next arrival-and-start minus (end + drive)."""
    return [(b.start_s - a.end_s - b.travel_s) / 60 for a, b in pairwise(route.stops)]


def carer_days(scenario: Scenario, solution: Solution) -> list[CarerDay]:
    """One record per carer in the scenario, including carers given no visits that day."""
    routes = {r.carer_ref: r for r in solution.routes}
    days = []
    for carer in scenario.carers:
        route = routes.get(carer.carer_ref, Route(carer.carer_ref, 0, ()))
        gaps = _gaps_min(route)
        familiar = [
            familiarity(scenario.client(st.client_ref), carer.carer_ref) is not Familiarity.NEW
            for st in route.stops
        ]
        days.append(
            CarerDay(
                seed=scenario.seed,
                carer_ref=carer.carer_ref,
                skills=len(carer.skills) - 1,
                shift_min=carer.shift_end - carer.shift_start,
                visits=len(route.stops),
                service_min=route.service_s / 60,
                drive_min=route.travel_s / 60,
                gap_min=sum(gaps),
                longest_gap_min=max(gaps, default=0.0),
                split_day=max(gaps, default=0.0) >= SPLIT_GAP_MIN,
                familiar_share=sum(familiar) / len(familiar) if familiar else None,
            )
        )
    return days
