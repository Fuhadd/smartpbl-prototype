"""Generate a synthetic carer workforce with a known attrition mechanism (Step 3.1).

Usage: uv run python -m scripts.generate_workforce [--seed 42] [--n 1000]
Reads data/workforce/tier2_carer_days.json (from scripts.calibrate_workforce) and writes
train.csv, test.csv (stratified 80/20) and oracle.csv to data/workforce/.

How a carer is made:
  1. Working conditions. The carer has a "home round": one Tier 2 carer-day. Over 13 weeks
     each shift is that round (p=HOME_ROUND_P) or another solved day on the same rota.
     Drive, gap, visit, split and familiarity features are averages over those shifts,
     so every working-conditions number comes from real solver output.
  2. Employment. Age band, tenure, contract, shifts per week and short-notice changes are
     drawn from stated assumptions (the data card lists them). Younger carers have shorter
     tenure and more zero-hours contracts, so age is correlated with real risk factors.
  3. Label. A ground-truth logistic model, GROUND_TRUTH below, plus a latent factor U the
     data doesn't contain (caring duties, a better offer, health). Age has no direct effect.

Everything a model "discovers" in Tier 3 was put here first. That is the point: with a
known mechanism we can check whether the pipeline recovers it (note 16, circularity).
"""

import argparse
import json
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from app.workforce.data import FEATURES, LABEL, AgeBand, CarerRecord

SEED = 42
N_CARERS = 1000
TEST_SIZE = 0.2
DIR = Path("data/workforce")
CALIBRATION = DIR / "tier2_carer_days.json"
WEEKS = 13  # observation window before the snapshot
HOME_ROUND_P = 0.6
TARGET_RATE = 0.30  # 12-month leaver rate; see the data card for the anchor
LATENT_SD = 1.0  # unobserved factor U on the log-odds scale

AGE_P = {AgeBand.A18_24: 0.12, AgeBand.A25_39: 0.33, AgeBand.A40_54: 0.33, AgeBand.A55_PLUS: 0.22}
MEDIAN_TENURE = {AgeBand.A18_24: 9, AgeBand.A25_39: 18, AgeBand.A40_54: 30, AgeBand.A55_PLUS: 42}
TENURE_SIGMA = 0.9  # lognormal
MAX_TENURE = {AgeBand.A18_24: 72, AgeBand.A25_39: 240, AgeBand.A40_54: 400, AgeBand.A55_PLUS: 480}
ZERO_HOURS_P = {
    AgeBand.A18_24: 0.55,
    AgeBand.A25_39: 0.40,
    AgeBand.A40_54: 0.35,
    AgeBand.A55_PLUS: 0.30,
}
SHIFTS = {False: ([4, 5], [0.4, 0.6]), True: ([2, 3, 4, 5], [0.2, 0.3, 0.3, 0.2])}
SHORT_NOTICE_RATE = {False: 1.0, True: 2.5}  # Poisson mean per month

# Ground truth: each term's contribution to the log-odds of leaving within 12 months.
# Constants are fixed (not fitted to the data), so the mechanism is the same for any seed.
Row = dict[str, float]
GROUND_TRUTH: dict[str, Callable[[Row], float]] = {
    "new starter (tenure < 6 months)": lambda r: 1.2 * (r["tenure_months"] < 6),
    "first year (6-11 months)": lambda r: 0.6 * (6 <= r["tenure_months"] < 12),
    "long tenure, per log-year past 1": lambda r: -0.3 * math.log(max(r["tenure_months"], 12) / 12),
    "zero-hours contract": lambda r: 0.5 * r["zero_hours"],
    "driving, per minute/shift over 40": lambda r: 0.025 * (r["drive_min_per_shift"] - 40),
    "unpaid gaps, per minute/shift over 90": lambda r: 0.008 * (r["gap_min_per_shift"] - 90),
    "split-shift share": lambda r: 0.8 * r["split_shift_share"],
    "familiar clients, vs 55% share": lambda r: -1.2 * (r["familiar_share"] - 0.55),
    "short-notice changes above 2/month": lambda r: (
        0.3 * max(0.0, r["short_notice_changes_per_month"] - 2)
    ),
    "  extra if zero-hours (interaction)": lambda r: (
        0.3 * r["zero_hours"] * max(0.0, r["short_notice_changes_per_month"] - 2)
    ),
}
NULL_FEATURES = ("late_shift", "skills_count", "visits_per_shift", "shifts_per_week")


def load_calibration() -> pd.DataFrame:
    days = pd.DataFrame(json.loads(CALIBRATION.read_text(encoding="utf-8"))["carer_days"])
    return days[days.visits > 0].reset_index(drop=True)  # a round is a day with work


def _working_conditions(rng: np.random.Generator, days: pd.DataFrame, n_shifts: int) -> Row:
    home = days.iloc[rng.integers(len(days))]
    same_rota = days[days.shift_min == home.shift_min]
    picks = [
        home if rng.random() < HOME_ROUND_P else same_rota.iloc[rng.integers(len(same_rota))]
        for _ in range(n_shifts)
    ]
    shifts = pd.DataFrame(picks)
    familiar = (shifts.familiar_share * shifts.visits).sum() / shifts.visits.sum()
    return {
        "late_shift": _is_late(home),
        "skills_count": int(home.skills),
        "paid_min_per_shift": float((shifts.service_min + shifts.drive_min).mean()),
        "visits_per_shift": round(float(shifts.visits.mean()), 2),
        "drive_min_per_shift": round(float(shifts.drive_min.mean()), 1),
        "gap_min_per_shift": round(float(shifts.gap_min.mean()), 1),
        "split_shift_share": round(float(shifts.split_day.mean()), 3),
        "familiar_share": round(float(familiar), 3),
    }


def _is_late(day: pd.Series) -> bool:
    return int(day.shift_min) == 420  # 15:00-22:00 is the 7-hour rota in Tier 2


def logit_observed(r: Row) -> float:
    """Ground-truth log-odds from observed features, before the intercept and U."""
    return sum(term(r) for term in GROUND_TRUTH.values())


def oracle_probability(z: np.ndarray, intercept: float) -> np.ndarray:
    """P(leave | observed features) = E_U[sigmoid(intercept + z + U)], U ~ N(0, LATENT_SD^2).
    The best calibrated probability any model of these features could output. Computed by
    Gauss-Hermite quadrature over U."""
    nodes, weights = np.polynomial.hermite_e.hermegauss(40)
    weights = weights / weights.sum()
    x = intercept + z[:, None] + LATENT_SD * nodes[None, :]
    return (weights / (1 + np.exp(-x))).sum(axis=1)


def solve_intercept(z: np.ndarray, target: float = TARGET_RATE) -> float:
    lo, hi = -10.0, 10.0
    for _ in range(60):  # bisection: the mean probability rises with the intercept
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if oracle_probability(z, mid).mean() < target else (lo, mid)
    return (lo + hi) / 2


def generate(seed: int = SEED, n: int = N_CARERS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (records, oracle). Records validate against CarerRecord."""
    rng = np.random.default_rng(seed)
    days = load_calibration()
    bands = list(AGE_P)
    rows: list[Row] = []
    for i in range(1, n + 1):
        age = bands[rng.choice(len(bands), p=list(AGE_P.values()))]
        tenure = math.exp(rng.normal(math.log(MEDIAN_TENURE[age]), TENURE_SIGMA))
        zero_hours = bool(rng.random() < ZERO_HOURS_P[age])
        options, probs = SHIFTS[zero_hours]
        per_week = int(rng.choice(options, p=probs))
        wc = _working_conditions(rng, days, per_week * WEEKS)
        rows.append(
            {
                "carer_ref": f"WF-{i:04d}",
                "tenure_months": int(min(max(round(tenure), 1), MAX_TENURE[age])),
                "zero_hours": zero_hours,
                "late_shift": wc["late_shift"],
                "shifts_per_week": per_week,
                "short_notice_changes_per_month": int(rng.poisson(SHORT_NOTICE_RATE[zero_hours])),
                "skills_count": wc["skills_count"],
                "weekly_paid_hours": round(per_week * wc["paid_min_per_shift"] / 60, 1),
                **{
                    k: wc[k]
                    for k in (
                        "visits_per_shift",
                        "drive_min_per_shift",
                        "gap_min_per_shift",
                        "split_shift_share",
                        "familiar_share",
                    )
                },
                "age_band": age.value,
            }
        )
    z = np.array([logit_observed(r) for r in rows])
    intercept = solve_intercept(z)
    u = rng.normal(0, LATENT_SD, n)
    p_actual = 1 / (1 + np.exp(-(intercept + z + u)))
    left = rng.random(n) < p_actual
    for r, y in zip(rows, left, strict=True):
        r[LABEL] = bool(y)
        CarerRecord.model_validate(r)
    records = pd.DataFrame(rows)
    oracle = pd.DataFrame(
        {
            "carer_ref": records.carer_ref,
            "intercept": round(intercept, 6),
            "logit_observed": np.round(z, 6),
            "p_oracle": np.round(oracle_probability(z, intercept), 6),
        }
    )
    return records, oracle


def split(records: pd.DataFrame, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = train_test_split(
        records, test_size=TEST_SIZE, stratify=records[LABEL], random_state=seed
    )
    return train.sort_values("carer_ref"), test.sort_values("carer_ref")


def summary(records: pd.DataFrame, oracle: pd.DataFrame, test: pd.DataFrame) -> list[str]:
    o = oracle.set_index("carer_ref").loc[test.carer_ref]
    lines = [
        f"carers {len(records)}, leavers {records[LABEL].sum()} ({records[LABEL].mean():.1%})",
        f"test {len(test)}, leavers {test[LABEL].sum()} ({test[LABEL].mean():.1%})",
        f"intercept {oracle.intercept.iloc[0]:.3f}",
        f"oracle ROC-AUC on test (best possible from these features): "
        f"{roc_auc_score(test[LABEL], o.p_oracle):.3f}; on all carers "
        f"{roc_auc_score(records[LABEL], oracle.p_oracle):.3f}",
        "",
        "ground-truth term contributions to log-odds (SD across carers = importance):",
        *(
            f"  {name:40s} SD {records.apply(lambda r, t=term: t(r), axis=1).std():.3f}"
            for name, term in GROUND_TRUTH.items()
        ),
        f"  {'latent U (unobserved)':40s} SD {LATENT_SD:.3f}",
        "",
        "leaver rate by age band (no direct effect; differences come via tenure/contract):",
        records.groupby("age_band")[LABEL].agg(["count", "mean"]).round(3).to_string(),
        "",
        "leaver rate by contract:",
        records.groupby("zero_hours")[LABEL].agg(["count", "mean"]).round(3).to_string(),
        "",
        records[list(FEATURES)].astype(float).describe().round(2).T.to_string(),
    ]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_CARERS)
    args = ap.parse_args()
    records, oracle = generate(args.seed, args.n)
    train, test = split(records, args.seed)
    DIR.mkdir(parents=True, exist_ok=True)
    train.to_csv(DIR / "train.csv", index=False)
    test.to_csv(DIR / "test.csv", index=False)
    oracle.to_csv(DIR / "oracle.csv", index=False)
    print("\n".join(summary(records, oracle, test)))


if __name__ == "__main__":
    main()
