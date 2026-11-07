"""Shared reads of saved schedule runs: the latest run and the committed sample day.

Runs store a keyed hash of their input, not the scenario (data minimisation, Step 2.6).
Visit details (windows, tasks) and locations are therefore only known for runs whose hash
matches the committed synthetic sample. Used by the schedule API and the carer app API.
"""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.log import input_hash
from app.matching.data import Scenario
from app.matching.models import ScheduleRun

SAMPLE_SCENARIO = Path("data/scheduling/scenario.json")


@lru_cache(maxsize=1)
def sample_scenario() -> tuple[Scenario, str]:
    """The committed sample day and its input HMAC (as stored on runs solved from it)."""
    scenario = Scenario.model_validate_json(SAMPLE_SCENARIO.read_text(encoding="utf-8"))
    return scenario, input_hash(scenario.model_dump_json())


def latest_run(session: Session) -> ScheduleRun | None:
    return session.scalars(select(ScheduleRun).order_by(ScheduleRun.created_at.desc())).first()


def sample_for(run: ScheduleRun) -> Scenario | None:
    """The sample scenario if `run` was solved from it, else None."""
    scenario, digest = sample_scenario()
    return scenario if run.scenario_hash == digest else None
