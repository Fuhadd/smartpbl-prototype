"""Workforce record schema for attrition prediction (Tier 3).

One row per carer at a snapshot date. Features summarise the 13 weeks before the snapshot;
the label says whether the carer left in the 12 months after it. Nothing measured after
the snapshot may become a feature (leakage: see ADR-020).

`age_band` is a protected characteristic (Equality Act 2010). It is kept only to audit
the model for indirect discrimination in Step 3.3 and is never a model input.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgeBand(StrEnum):
    A18_24 = "18-24"
    A25_39 = "25-39"
    A40_54 = "40-54"
    A55_PLUS = "55+"


class CarerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    carer_ref: str = Field(pattern=r"^WF-\d{4}$")
    # Employment (workforce system; not in Tier 2)
    tenure_months: int = Field(ge=1, le=480)
    zero_hours: bool
    late_shift: bool  # mostly works the 15:00-22:00 rota
    shifts_per_week: int = Field(ge=1, le=7)
    short_notice_changes_per_month: int = Field(ge=0)  # rota changes with < 48 h notice
    skills_count: int = Field(ge=0, le=4)  # skills beyond personal care
    # Working conditions (aggregated from Tier 2 solver carer-days)
    weekly_paid_hours: float = Field(ge=0)
    visits_per_shift: float = Field(ge=0)
    drive_min_per_shift: float = Field(ge=0)
    gap_min_per_shift: float = Field(ge=0)  # unpaid waiting between visits
    split_shift_share: float = Field(ge=0, le=1)  # shifts with a gap of 90+ minutes
    familiar_share: float = Field(ge=0, le=1)  # visits to clients who know the carer
    # Audit only, never a feature
    age_band: AgeBand
    # Label
    left_within_12m: bool


FEATURES: tuple[str, ...] = (
    "tenure_months",
    "zero_hours",
    "late_shift",
    "shifts_per_week",
    "short_notice_changes_per_month",
    "skills_count",
    "weekly_paid_hours",
    "visits_per_shift",
    "drive_min_per_shift",
    "gap_min_per_shift",
    "split_shift_share",
    "familiar_share",
)
LABEL = "left_within_12m"
PROTECTED = ("age_band",)
