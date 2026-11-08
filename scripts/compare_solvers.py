"""Step 2.5: greedy nearest-available-carer vs OR-Tools, over several synthetic days.

Usage: uv run python -m scripts.compare_solvers [--days 5] [--time-limit 10]
Seeds are tried from 42 upwards; scenarios that fail validation (skill-mix gaps) are skipped
and reported, until --days valid days are collected. Travel
matrices come from OSRM (cached in data/scheduling/travel/) when reachable, otherwise the
calibrated haversine fallback; the backend is recorded per day.
Writes docs/results/tier2_comparison.md and docs/figures/tier2_comparison.png.
"""

import argparse
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.matching.check import check_solution
from app.matching.continuity import continuity_stats
from app.matching.data import Scenario, validate_scenario
from app.matching.greedy import solve_greedy
from app.matching.solver import Solution, SolverParams, solve
from app.matching.travel import (
    OSRMClient,
    TravelMatrix,
    cached_matrix,
    haversine_matrix,
    scenario_points,
)
from scripts.build_travel_matrix import CACHE_DIR, MD5_FILE, OSRM_URL
from scripts.generate_schedule import generate

RESULTS = Path("docs/results/tier2_comparison.md")
FIGURE = Path("docs/figures/tier2_comparison.png")
CONTINUITY_W_MIN = 15  # the knee of the seed-42 trade-off curve (ADR-017)
SYSTEMS = [
    "Greedy (nearest available)",
    "OR-Tools, w=0",
    f"OR-Tools, w={CONTINUITY_W_MIN}, two-phase",
]
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a"]  # validated categorical slots 1-3
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"


@dataclass(frozen=True)
class Result:
    seed: int
    system: str
    dropped: int
    critical_dropped: int
    drive_min: float
    familiar_pct: float
    utilisation: float  # (visit + drive time) / total shift time of all carers
    wall_s: float
    backend: str


def matrix_for(s: Scenario) -> TravelMatrix:
    points = scenario_points(s.carers, s.clients)
    if MD5_FILE.exists():
        client = OSRMClient(OSRM_URL, data_version=MD5_FILE.read_text().split()[0][:12])
        try:
            return cached_matrix(points, client.backend, client.table, CACHE_DIR)
        except httpx.HTTPError:
            pass  # OSRM not running and not cached: fall back
    return haversine_matrix(points)


def measure(seed: int, system: str, s: Scenario, m: TravelMatrix, sol: Solution) -> Result:
    if problems := check_solution(s, m, sol):
        raise SystemExit(f"seed {seed} {system}: invalid solution {problems[:3]}")
    capacity = sum((c.shift_end - c.shift_start) * 60 for c in s.carers)
    busy = sum(r.service_s + r.travel_s for r in sol.routes)
    critical = {v.visit_id for v in s.visits if v.time_critical}
    return Result(
        seed=seed,
        system=system,
        dropped=len(sol.dropped),
        critical_dropped=len(critical & set(sol.dropped)),
        drive_min=sol.travel_s / 60,
        familiar_pct=continuity_stats(s, sol).familiar_pct,
        utilisation=busy / capacity,
        wall_s=sol.wall_s,
        backend=m.backend.split(":")[0],
    )


def chart(results: list[Result], seeds: list[int]) -> None:
    metrics = [
        ("dropped", "Unassigned visits", 1),
        ("drive_min", "Driving (min/day)", 1),
        ("familiar_pct", "Familiar carer (% of served)", 100),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), facecolor=SURFACE)
    width = 0.8 / len(SYSTEMS)
    x = np.arange(len(seeds))
    for ax, (attr, title, scale) in zip(axes, metrics, strict=True):
        ax.set_facecolor(SURFACE)
        for i, system in enumerate(SYSTEMS):
            vals = [
                getattr(next(r for r in results if r.seed == sd and r.system == system), attr)
                * scale
                for sd in seeds
            ]
            ax.bar(x + (i - 1) * width, vals, width - 0.03, color=COLOURS[i], label=system)
        ax.set_xticks(x, [str(sd) for sd in seeds], fontsize=8)
        ax.set_xlabel("Day (scenario seed)", color=MUTED, fontsize=8)
        ax.set_title(title, loc="left", color=INK, fontsize=10)
        ax.yaxis.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, labelcolor=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, labelcolor=INK, fontsize=9, ncol=3,
               loc="upper left", bbox_to_anchor=(0.01, 0.93))  # fmt: skip
    fig.suptitle(f"Greedy vs OR-Tools across {len(seeds)} synthetic days", x=0.01, ha="left",
                 color=INK, fontsize=11)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--time-limit", type=float, default=10.0)
    args = ap.parse_args()

    results: list[Result] = []
    used, skipped = [], []
    seed = 41
    while len(used) < args.days:
        seed += 1
        s = generate(seed)
        if problems := validate_scenario(s):
            skipped.append((seed, len(problems)))
            continue
        used.append(seed)
        m = matrix_for(s)
        base = solve(s, m, SolverParams(time_limit_s=args.time_limit))
        # Two-phase (lexicographic, ADR-017): warm-start the continuity solve from the
        # coverage-first solution, so adding continuity can never cost a visit.
        cont_params = SolverParams(
            time_limit_s=args.time_limit, continuity_weight_s=CONTINUITY_W_MIN * 60
        )
        cont = solve(s, m, cont_params, initial=base)
        cont = replace(cont, wall_s=base.wall_s + cont.wall_s)
        runs = [(SYSTEMS[0], solve_greedy(s, m)), (SYSTEMS[1], base), (SYSTEMS[2], cont)]
        for system, sol in runs:
            r = measure(seed, system, s, m, sol)
            results.append(r)
            print(f"seed {seed} {system:28s} dropped {r.dropped:2d} drive {r.drive_min:4.0f}")

    out = [
        "# Tier 2 comparison: greedy vs OR-Tools",
        "",
        f"- Days (seeds): {', '.join(map(str, used))}"
        + (
            f"; skipped (invalid scenario): {', '.join(f'{s} ({n} problems)' for s, n in skipped)}"
            if skipped
            else ""
        )
        + ".",
        f"- OR-Tools: PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH, {args.time_limit:.0f} s; "
        f"continuity weight {CONTINUITY_W_MIN} min (the knee from ADR-017), solved two-phase "
        "(warm-started from the w=0 solution; runtime is the sum of both phases).",
        "- Every solution passed the independent checker. Utilisation = (visit + driving) time "
        "/ total shift time of all carers.",
        "- Time-limited search: single numbers vary by a few % between reruns (see ADR-017).",
        "",
        "## Mean over days",
        "",
        "| System | Unassigned | Time-critical unassigned | Driving (min) | Familiar carer "
        "| Utilisation | Runtime (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for system in SYSTEMS:
        rs = [r for r in results if r.system == system]
        out.append(
            f"| {system} | {statistics.mean(r.dropped for r in rs):.1f} "
            f"| {statistics.mean(r.critical_dropped for r in rs):.1f} "
            f"| {statistics.mean(r.drive_min for r in rs):.0f} "
            f"| {statistics.mean(r.familiar_pct for r in rs):.1%} "
            f"| {statistics.mean(r.utilisation for r in rs):.1%} "
            f"| {statistics.mean(r.wall_s for r in rs):.3f} |"
        )
    out += [
        "",
        "## Per day",
        "",
        "| Seed | Travel backend | System | Unassigned | Driving (min) | Familiar | Utilisation |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        out.append(
            f"| {r.seed} | {r.backend} | {r.system} | {r.dropped} | {r.drive_min:.0f} "
            f"| {r.familiar_pct:.1%} | {r.utilisation:.1%} |"
        )
    out += ["", "![Comparison](../figures/tier2_comparison.png)", ""]
    chart(results, used)
    RESULTS.write_text("\n".join(out), encoding="utf-8")
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
