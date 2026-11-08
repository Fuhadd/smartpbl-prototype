"""Step 3.1: solve the Tier 2 evaluation days and save per-carer-day working conditions.

Usage: uv run python -m scripts.calibrate_workforce [--days 5] [--time-limit 10]
Uses the same days (first 5 valid seeds from 42), travel matrices and production-like
configuration (OR-Tools, continuity weight 15 min, two-phase) as scripts/compare_solvers.

The output, data/workforce/tier2_carer_days.json, is committed. The workforce generator
reads it instead of re-solving, because time-limited search varies run to run (ADR-017):
re-solving would make the synthetic workforce non-reproducible.
"""

import argparse
import json
from pathlib import Path

from app.matching.check import check_solution
from app.matching.data import validate_scenario
from app.matching.solver import SolverParams, solve
from app.workforce.features import carer_days
from scripts.compare_solvers import CONTINUITY_W_MIN, matrix_for
from scripts.generate_schedule import generate

OUT = Path("data/workforce/tier2_carer_days.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--time-limit", type=float, default=10.0)
    args = ap.parse_args()

    records: list[dict[str, object]] = []
    seeds: list[int] = []
    backends: set[str] = set()
    seed = 41
    while len(seeds) < args.days:
        seed += 1
        s = generate(seed)
        if validate_scenario(s):
            continue
        m = matrix_for(s)
        base = solve(s, m, SolverParams(time_limit_s=args.time_limit))
        params = SolverParams(
            time_limit_s=args.time_limit, continuity_weight_s=CONTINUITY_W_MIN * 60
        )
        sol = solve(s, m, params, initial=base)
        if problems := check_solution(s, m, sol):
            raise SystemExit(f"seed {seed}: invalid solution {problems[:3]}")
        seeds.append(seed)
        backends.add(m.backend.split(":")[0])
        records += [d.as_dict() for d in carer_days(s, sol)]
        print(f"seed {seed}: {len(sol.dropped)} dropped, {sol.travel_s // 60} min driving")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "scripts/calibrate_workforce.py",
        "seeds": seeds,
        "solver": f"OR-Tools, w={CONTINUITY_W_MIN} min two-phase, {args.time_limit:.0f} s",
        "travel_backends": sorted(backends),
        "carer_days": records,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} carer-days to {OUT}")


if __name__ == "__main__":
    main()
