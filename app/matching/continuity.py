"""Continuity of care: how familiar each assigned carer is to the client.

Three levels (Step 2.4):
  preferred - named by the client or family (strongest);
  recent    - visited the client in the last 28 days (familiar, not chosen);
  new       - neither.
The solver penalises "new" by the full continuity weight and "recent" by half; "preferred"
costs nothing. The weight is in seconds of driving, so it reads as: "how much extra
driving would we accept to send a familiar carer instead of a stranger?"
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.matching.data import Client, Scenario

if TYPE_CHECKING:  # the solver imports this module, so avoid a runtime cycle
    from app.matching.solver import Solution

RECENT_SHARE = 0.5  # a recent (familiar, not preferred) carer costs half the penalty


class Familiarity(StrEnum):
    PREFERRED = "preferred"
    RECENT = "recent"
    NEW = "new"


def familiarity(client: Client, carer_ref: str) -> Familiarity:
    if carer_ref in client.preferred_carers:
        return Familiarity.PREFERRED
    if carer_ref in client.recent_carers:
        return Familiarity.RECENT
    return Familiarity.NEW


def penalty_s(client: Client, carer_ref: str, weight_s: int) -> int:
    level = familiarity(client, carer_ref)
    if level is Familiarity.PREFERRED:
        return 0
    if level is Familiarity.RECENT:
        return round(weight_s * RECENT_SHARE)
    return weight_s


@dataclass(frozen=True)
class ContinuityStats:
    served: int
    preferred: int
    recent: int
    new: int
    distinct_carers_per_client: float  # mean over clients with 2+ served visits

    @property
    def familiar_pct(self) -> float:  # the headline continuity metric
        return (self.preferred + self.recent) / self.served if self.served else 0.0

    @property
    def preferred_pct(self) -> float:
        return self.preferred / self.served if self.served else 0.0


def continuity_stats(scenario: Scenario, solution: "Solution") -> ContinuityStats:
    counts = dict.fromkeys(Familiarity, 0)
    carers_by_client: dict[str, set[str]] = {}
    for route in solution.routes:
        for stop in route.stops:
            client = scenario.client(stop.client_ref)
            counts[familiarity(client, route.carer_ref)] += 1
            carers_by_client.setdefault(stop.client_ref, set()).add(route.carer_ref)
    visits_by_client: dict[str, int] = {}
    for route in solution.routes:
        for stop in route.stops:
            visits_by_client[stop.client_ref] = visits_by_client.get(stop.client_ref, 0) + 1
    multi = [len(carers_by_client[c]) for c, n in visits_by_client.items() if n >= 2]
    return ContinuityStats(
        served=sum(counts.values()),
        preferred=counts[Familiarity.PREFERRED],
        recent=counts[Familiarity.RECENT],
        new=counts[Familiarity.NEW],
        distinct_carers_per_client=sum(multi) / len(multi) if multi else 0.0,
    )
