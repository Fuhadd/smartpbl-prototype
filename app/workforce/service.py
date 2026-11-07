"""Workforce risk service for the API (Step 3.4).

The served model is trained on first use from the committed training carers and cached
for the process lifetime (about 5 s, deterministic). It is not loaded from a pickle:
unpickling runs arbitrary code and ties the artefact to exact library versions, while
re-training from versioned data gives the same model every time (ADR-023). The version
string identifies the training data, hyperparameter grid and library versions.

"Current workforce" = the 200 held-out test carers, so every served score is out of
sample. The label and the protected attribute are never part of a response.
"""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from app.workforce.explain import (
    CarerExplanation,
    explain_carer,
    fit_final_model,
    make_explainer,
    shap_values,
)
from app.workforce.models import candidates, xy

DATA = Path("data/workforce")
MODEL_NAME = "attrition-hgb"
SUPPORT_SHARE = 0.2  # top 20% by risk are suggested for a supportive check-in (model card)


@dataclass(frozen=True)
class ScoredCarer:
    carer_ref: str
    rank: int  # 1 = highest risk
    risk: float
    support_priority: bool
    explanation: CarerExplanation


class WorkforceRisk:
    def __init__(self, train: pd.DataFrame, current: pd.DataFrame, version: str) -> None:
        self.version = version
        self.model: HistGradientBoostingClassifier = fit_final_model(train)
        sv = shap_values(make_explainer(self.model), current)
        risk = self.model.predict_proba(xy(current)[0])[:, 1]
        order = np.argsort(-risk, kind="stable")
        n_priority = round(len(current) * SUPPORT_SHARE)
        self.carers: dict[str, ScoredCarer] = {}
        for rank, i in enumerate(order, 1):
            row = current.iloc[i]
            self.carers[row.carer_ref] = ScoredCarer(
                carer_ref=row.carer_ref,
                rank=rank,
                risk=round(float(risk[i]), 3),
                support_priority=rank <= n_priority,
                explanation=explain_carer(sv, int(i), row, top=len(sv.feature_names)),
            )
        self.average_risk = round(float(risk.mean()), 3)

    def ranked(self) -> list[ScoredCarer]:
        return sorted(self.carers.values(), key=lambda c: c.rank)


def model_version(train_csv: Path) -> str:
    """Short digest of everything that determines the fitted model."""
    grid = candidates()["Gradient boosting (HGB)"]
    spec = {
        "data_sha256": hashlib.sha256(train_csv.read_bytes()).hexdigest(),
        "estimator": repr(grid.estimator),
        "grid": grid.param_grid,
        "sklearn": sklearn.__version__,
        "shap": shap.__version__,
    }
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


@lru_cache
def get_workforce_risk() -> WorkforceRisk:
    train_csv = DATA / "train.csv"
    return WorkforceRisk(
        pd.read_csv(train_csv), pd.read_csv(DATA / "test.csv"), model_version(train_csv)
    )
