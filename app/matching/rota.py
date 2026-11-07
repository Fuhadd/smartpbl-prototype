"""A carer's own day, read from the latest saved run (Step 5.6, carer app).

The carer app never sees another carer's route: everything here starts from the
signed-in user's `carer_ref`. Visit details (windows, tasks) and locations come from the
committed sample scenario, and only when the run was solved from it (see runs.py).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.matching.data import Scenario, Skill, Visit
from app.matching.models import ScheduleAssignment, ScheduleRun
from app.matching.runs import latest_run, sample_for

# What each required skill means on a visit, phrased for the carer.
TASKS: dict[Skill, tuple[str, str]] = {
    Skill.PERSONAL_CARE: ("Personal care", "Washing, dressing and toileting"),
    Skill.MEDICATION: ("Medication", "Administer as on the MAR chart, with water"),
    Skill.MANUAL_HANDLING: ("Moving and handling", "Hoist or transfer aid, two hands if needed"),
    Skill.DEMENTIA_CARE: ("Dementia support", "Calm routine, offer simple choices"),
    Skill.CATHETER_CARE: ("Catheter care", "Check, empty and record output"),
}
# Shown first: what the carer must not miss.
TASK_ORDER = (Skill.MEDICATION, Skill.CATHETER_CARE, Skill.MANUAL_HANDLING,
              Skill.DEMENTIA_CARE, Skill.PERSONAL_CARE)  # fmt: skip


@dataclass(frozen=True)
class RotaVisit:
    assignment: ScheduleAssignment
    visit: Visit | None  # None when the run isn't the sample day
    scenario: Scenario | None

    @property
    def tasks(self) -> list[Skill]:
        if self.visit is None:
            return []
        return [s for s in TASK_ORDER if s in self.visit.required_skills]


@dataclass(frozen=True)
class CarerDay:
    run: ScheduleRun
    visits: list[RotaVisit]

    def find(self, visit_id: str) -> RotaVisit | None:
        return next((v for v in self.visits if v.assignment.visit_id == visit_id), None)


def carer_day(session: Session, carer_ref: str) -> CarerDay | None:
    """The carer's visits in the latest run, in order; None if no rota is saved yet."""
    run = latest_run(session)
    if run is None:
        return None
    scenario = sample_for(run)
    visits = {v.visit_id: v for v in scenario.visits} if scenario else {}
    mine = sorted(
        (a for a in run.assignments if a.carer_ref == carer_ref), key=lambda a: a.sequence
    )
    return CarerDay(run, [RotaVisit(a, visits.get(a.visit_id), scenario) for a in mine])
