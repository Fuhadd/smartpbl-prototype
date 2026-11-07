"""Step 2.4: sweep the continuity weight and trace the travel vs continuity trade-off.

Usage: uv run python -m scripts.sweep_continuity [--time-limit 30] [--quick]
Writes docs/results/tier2_continuity.md and docs/figures/tier2_pareto.png.

Continuity is reported two ways:
  - familiar share of ALL visits (preferred or recent carer) - same unit as the proven
    travel-free ceiling, and dropped visits count against it;
  - familiar share of SERVED visits - the usual operational metric.
"""

import argparse
import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.matching.bounds import travel_free_continuity_bound, travel_free_drop_bound
from app.matching.check import check_solution
from app.matching.continuity import ContinuityStats, continuity_stats
from app.matching.solver import Solution, SolverParams, solve
from scripts.solve_baseline import load

WEIGHTS_MIN = [0, 1, 2, 5, 10, 15, 20, 30, 45, 60]
RESULTS = Path("docs/results/tier2_continuity.md")
FIGURE = Path("docs/figures/tier2_pareto.png")
TRADEOFF = Path("data/scheduling/tradeoff.json")  # served by GET /schedule/tradeoff
INK, MUTED, GRID, SURFACE, BLUE, ORANGE = (
    "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb", "#2a78d6", "#eb6834",
)  # fmt: skip


@dataclass(frozen=True)
class Point:
    weight_min: int
    solution: Solution
    stats: ContinuityStats
    n_visits: int

    @property
    def drive_min(self) -> float:
        return self.solution.travel_s / 60

    @property
    def familiar_all(self) -> float:
        return (self.stats.preferred + self.stats.recent) / self.n_visits

    @property
    def dropped(self) -> int:
        return len(self.solution.dropped)


def dominates(q: Point, p: Point) -> bool:
    """q is at least as good as p on all three objectives and better on one."""
    no_worse = (
        q.drive_min <= p.drive_min and q.familiar_all >= p.familiar_all and q.dropped <= p.dropped
    )
    better = q.drive_min < p.drive_min or q.familiar_all > p.familiar_all or q.dropped < p.dropped
    return no_worse and better


def pareto(points: list[Point]) -> list[Point]:
    """Non-dominated points over (driving, familiar visits, drops)."""
    front = [p for p in points if not any(dominates(q, p) for q in points)]
    return sorted(front, key=lambda p: p.drive_min)


def chart(points: list[Point], front: list[Point], ceiling: float) -> None:
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    on_front = {p.weight_min for p in front}
    ax.plot([p.drive_min for p in front], [p.familiar_all * 100 for p in front], color=BLUE,
            lw=2, zorder=1, label="Trade-off curve (non-dominated)")  # fmt: skip
    groups: dict[tuple[float, float], list[Point]] = {}
    for p in points:
        # Points within ~5 min and ~1 point share one label so annotations don't collide.
        groups.setdefault((round(p.drive_min / 5), round(p.familiar_all * 100)), []).append(p)
    for same in groups.values():
        x, y = same[0].drive_min, same[0].familiar_all
        filled = any(p.weight_min in on_front for p in same)
        ax.scatter(x, y * 100, s=64, zorder=2, linewidths=2,
                   color=BLUE if filled else SURFACE, edgecolors=BLUE)  # fmt: skip
        label = "w=" + ", ".join(str(p.weight_min) for p in same)
        drops = {p.dropped for p in same}
        if drops != {0}:
            label += f" ({max(drops)} dropped)"
        ax.annotate(label, (x, y * 100), xytext=(6, -12), textcoords="offset points",
                    fontsize=8, color=MUTED)  # fmt: skip
    ax.axhline(ceiling * 100, color=ORANGE, lw=1.5, ls="--",
               label=f"Proven ceiling (zero travel): {ceiling:.0%}")  # fmt: skip
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Total driving (min/day)", color=MUTED)
    ax.set_ylabel("Visits by a familiar carer (%)", color=MUTED)
    ax.set_title("Travel vs continuity: continuity weight w in minutes per unfamiliar visit",
                 loc="left", color=INK, fontsize=11)  # fmt: skip
    ax.legend(frameon=False, labelcolor=INK, loc="lower right")
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def write_tradeoff(
    points: list[Point], front_w: set[int], name: str, backend: str, limit: float, n: int
) -> None:
    """The sweep as data, for the schedule screen's trade-off panel."""
    data = {
        "scenario_name": name,
        "matrix_backend": backend,
        "time_limit_s": limit,
        "visits": n,
        "points": [
            {
                "weight_min": p.weight_min,
                "drive_min": round(p.drive_min),
                "familiar_pct": round(p.stats.familiar_pct, 3),
                "preferred_pct": round(p.stats.preferred_pct, 3),
                "dropped": p.dropped,
                "pareto": p.weight_min in front_w,
            }
            for p in points
        ],
    }
    TRADEOFF.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=30.0)
    ap.add_argument("--quick", action="store_true", help="3 weights, 2 s each (smoke run)")
    args = ap.parse_args()
    weights = [0, 10, 30] if args.quick else WEIGHTS_MIN
    limit = 2.0 if args.quick else args.time_limit
    full, m = load()
    # Lexicographic step 1: fix coverage. Solve once without continuity, keep the visits it
    # serves, and sweep only over those, so every point serves the same visits and the
    # curve compares travel against continuity alone (drop-count noise removed). Each run
    # warm-starts from the reference routes, so coverage can only be kept, never lost.
    reference = solve(full, m, SolverParams(time_limit_s=limit))
    kept = tuple(v for v in full.visits if v.visit_id not in set(reference.dropped))
    scenario = full.model_copy(update={"visits": kept})
    n = len(kept)
    print(f"coverage fixed: {n} of {len(full.visits)} visits ({len(reference.dropped)} dropped)")

    points = []
    for w in weights:
        params = SolverParams(time_limit_s=limit, continuity_weight_s=w * 60)
        sol = solve(scenario, m, params, initial=reference)  # warm start keeps coverage
        if problems := check_solution(scenario, m, sol):
            raise SystemExit(f"w={w}: invalid solution: {problems[:3]}")
        points.append(Point(w, sol, continuity_stats(scenario, sol), n))
        print(f"w={w:>2} min: dropped {len(sol.dropped)}, drive {sol.travel_s / 60:.0f} min")
    front = pareto(points)
    ceiling = travel_free_continuity_bound(scenario)
    min_drop = travel_free_drop_bound(full).min_dropped
    chart(points, front, ceiling.max_familiar_pct)

    out = [
        "# Tier 2 continuity sweep: travel vs continuity of care",
        "",
        f"- Scenario `{full.name}`; travel `{m.backend}`; "
        f"{points[0].solution.params.metaheuristic}, {limit:.0f} s per point.",
        f"- **Coverage fixed first (lexicographic):** a continuity-blind solve served {n} of "
        f"{len(full.visits)} visits; the sweep schedules exactly those {n}, so points differ "
        "only in travel and continuity. Percentages below are of these visits.",
        "- Weight *w* = minutes of driving the solver will trade to avoid one visit by a new "
        "carer (a recent carer costs w/2, a preferred carer 0).",
        f"- **Proven ceilings (zero travel, CP-SAT):** at most {ceiling.max_familiar} of these "
        f"{n} visits ({ceiling.max_familiar_pct:.1%}) can be covered by a familiar carer; on "
        f"the full day at least {min_drop} visits must be dropped.",
        "",
        "| w (min) | Dropped | Drive (min) | Familiar, % of visits | Familiar, % of served "
        "| Preferred, % of served | Distinct carers per multi-visit client | Pareto |",
        "|---|---|---|---|---|---|---|---|",
    ]
    front_w = {p.weight_min for p in front}
    for p in points:
        out.append(
            f"| {p.weight_min} | {p.dropped} | {p.drive_min:.0f} | {p.familiar_all:.1%} "
            f"| {p.stats.familiar_pct:.1%} | {p.stats.preferred_pct:.1%} "
            f"| {p.stats.distinct_carers_per_client:.2f} "
            f"| {'yes' if p.weight_min in front_w else ''} |"
        )
    out += [
        "",
        "## Marginal cost along the curve (non-dominated points)",
        "",
        "| From w | To w | Extra driving (min) | Extra familiar visits | Extra drops "
        "| Minutes per extra familiar visit |",
        "|---|---|---|---|---|---|",
    ]
    for a, b in pairwise(front):
        dv = round((b.familiar_all - a.familiar_all) * n)
        dd = b.drive_min - a.drive_min
        rate = f"{dd / dv:.1f}" if dv > 0 else "n/a"
        out.append(
            f"| {a.weight_min} | {b.weight_min} | {dd:+.0f} | {dv:+d} "
            f"| {b.dropped - a.dropped:+d} | {rate} |"
        )
    out += ["", "![Travel vs continuity](../figures/tier2_pareto.png)", ""]
    write_tradeoff(points, front_w, full.name, m.backend, limit, n)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text("\n".join(out), encoding="utf-8")
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
