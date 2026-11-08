"""GET /workforce/risk and GET /workforce/{carer_ref}/explanation (Step 3.4).

Every response carries the supportive-use notice from the model card, and every read is
audited (who viewed which carers' risk), because this is profiling of employees. Neither
the label (future outcome) nor the protected attribute (age band) is ever returned.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_workforce, require
from app.audit.log import record
from app.audit.models import EventType, SubjectType
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session
from app.workforce.explain import Reason
from app.workforce.service import (
    MODEL_NAME,
    SUPPORT_SHARE,
    RiskBand,
    ScoredCarer,
    WorkforceRisk,
)

router = APIRouter(
    prefix="/workforce", tags=["workforce"], dependencies=[Depends(get_current_user)]
)
SessionDep = Annotated[Session, Depends(get_session)]
WorkforceDep = Annotated[WorkforceRisk, Depends(get_workforce)]
ViewerDep = Annotated[User, Depends(require(Permission.WORKFORCE_READ))]

USE_NOTICE = (
    "Supportive use only. A higher score suggests where to offer help with working "
    "conditions (rota notice, unpaid gaps, regular clients, induction). It must not be used "
    "to reduce hours, discipline, or make recruitment decisions. Explanations describe the "
    "model, not proven causes. Synthetic prototype: not for use on real carers."
)
# Only suggest support for factors that add at least this much (about +2 percentage points
# at a 30% base rate): small contributions are the likeliest to be noise (ADR-022).
MIN_SUPPORT_LOG_ODDS = 0.1
CAVEATS = (
    "Scores are probabilities from a model trained on synthetic data.",
    "Factors that measure the same thing (unpaid gaps and split shifts) can swap credit.",
    "Small contributions may reflect noise; discuss factors with the carer before acting.",
)


class ModelInfo(BaseModel):
    name: str
    version: str
    synthetic: bool = True


class FactorOut(BaseModel):
    feature: str
    label: str
    value: str
    log_odds: float
    points: float  # percentage points of (risk - baseline_risk); rows add up to that gap
    team_value: str  # team median (or share for yes/no factors), for comparison
    direction: str
    provider_can_change: bool
    support: str | None


class RiskItem(BaseModel):
    carer_ref: str
    rank: int
    risk: float
    support_priority: bool
    band: RiskBand
    top_factors: list[FactorOut]


class RiskList(BaseModel):
    model: ModelInfo
    use_notice: str
    average_risk: float
    support_share: float
    total: int
    carers: list[RiskItem]


class ExplanationOut(BaseModel):
    model: ModelInfo
    use_notice: str
    carer_ref: str
    rank: int
    of: int
    risk: float
    baseline_risk: float  # where the explanation starts (SHAP base value as a probability)
    average_risk: float  # mean predicted risk over the current workforce
    support_priority: bool
    band: RiskBand
    factors: list[FactorOut]
    suggested_support: list[str]
    caveats: list[str]


def _factor(r: Reason, w: WorkforceRisk) -> FactorOut:
    return FactorOut(
        feature=r.feature,
        label=r.label,
        value=r.value,
        log_odds=r.log_odds,
        points=r.points,
        team_value=w.team_values[r.feature],
        direction=r.direction,
        provider_can_change=r.lever,
        support=r.support,
    )


def _model(w: WorkforceRisk) -> ModelInfo:
    return ModelInfo(name=MODEL_NAME, version=w.version)


def _audit(
    session: Session,
    event: EventType,
    actor: str,
    w: WorkforceRisk,
    output: dict,
    carer_ref: str | None = None,
) -> None:
    subject = (SubjectType.CARER, carer_ref) if carer_ref else None
    record(session, event, actor=actor, output=output, model_name=MODEL_NAME,
           model_version=w.version, subject=subject)  # fmt: skip
    session.commit()


@router.get("/risk")
def list_risk(
    viewer: ViewerDep,
    session: SessionDep,
    w: WorkforceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    priority_only: bool = False,
) -> RiskList:
    """Carers ranked by risk (highest first), each with its three largest factors."""
    carers: list[ScoredCarer] = w.ranked()
    if priority_only:
        carers = [c for c in carers if c.support_priority]
    page = carers[offset : offset + limit]
    _audit(session, EventType.WORKFORCE_RISK_VIEWED, f"user:{viewer.username}", w,
           {"carer_refs": [c.carer_ref for c in page], "offset": offset, "limit": limit,
            "priority_only": priority_only})  # fmt: skip
    return RiskList(
        model=_model(w),
        use_notice=USE_NOTICE,
        average_risk=w.average_risk,
        support_share=SUPPORT_SHARE,
        total=len(carers),
        carers=[
            RiskItem(
                carer_ref=c.carer_ref,
                rank=c.rank,
                risk=c.risk,
                support_priority=c.support_priority,
                band=c.band,
                top_factors=[_factor(r, w) for r in c.explanation.reasons[:3]],
            )
            for c in page
        ],
    )


@router.get("/{carer_ref}/explanation")
def explain(
    carer_ref: Annotated[str, Path(pattern=r"^WF-\d{4}$")],
    viewer: ViewerDep,
    session: SessionDep,
    w: WorkforceDep,
) -> ExplanationOut:
    """Every factor's contribution (log-odds; they add up to the score), with support
    actions for the provider-side factors that raise risk."""
    c = w.carers.get(carer_ref)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "carer not in the current workforce")
    _audit(session, EventType.WORKFORCE_EXPLANATION_VIEWED, f"user:{viewer.username}", w,
           {"carer_ref": c.carer_ref, "risk": c.risk, "rank": c.rank}, c.carer_ref)  # fmt: skip
    reasons = c.explanation.reasons
    support = list(
        dict.fromkeys(
            r.support
            for r in reasons
            if r.support and r.lever and r.log_odds >= MIN_SUPPORT_LOG_ODDS
        )
    )
    return ExplanationOut(
        model=_model(w),
        use_notice=USE_NOTICE,
        carer_ref=c.carer_ref,
        rank=c.rank,
        of=len(w.carers),
        risk=c.risk,
        baseline_risk=c.explanation.baseline_risk,
        average_risk=w.average_risk,
        support_priority=c.support_priority,
        band=c.band,
        factors=[_factor(r, w) for r in reasons],
        suggested_support=support,
        caveats=list(CAVEATS),
    )
