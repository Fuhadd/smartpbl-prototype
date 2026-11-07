"""Step 2.3 experiments: baseline VRPTW on the seed-42 scenario.

Usage: uv run python -m scripts.solve_baseline [--quick]
Compares first-solution strategies and metaheuristics, diagnoses dropped visits against a
proven travel-free lower bound, runs two staffing what-ifs, and draws the routes.
Writes docs/results/tier2_baseline.md and docs/figures/tier2_baseline_routes.png.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from app.matching.bounds import travel_free_drop_bound
from app.matching.check import check_solution
from app.matching.data import Scenario, Skill, can_serve
from app.matching.solver import Solution, SolverParams, solve
from app.matching.travel import TravelMatrix, scenario_points
from scripts.generate_schedule import OUT as SCENARIO_PATH

TRAVEL_DIR = Path("data/scheduling/travel")
RESULTS = Path("docs/results/tier2_baseline.md")
FIGURE = Path("docs/figures/tier2_baseline_routes.png")
FIRST = [
    "PATH_CHEAPEST_ARC",
    "PARALLEL_CHEAPEST_INSERTION",
    "LOCAL_CHEAPEST_INSERTION",
    "SAVINGS",
    "CHRISTOFIDES",
]
META = ["GREEDY_DESCENT", "GUIDED_LOCAL_SEARCH", "SIMULATED_ANNEALING", "TABU_SEARCH"]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
SERVICE, TRAVEL, WAIT = "#2a78d6", "#eb6834", "#e1e0d9"


def load() -> tuple[Scenario, TravelMatrix]:
    scenario = Scenario.model_validate_json(SCENARIO_PATH.read_text(encoding="utf-8"))
    points = scenario_points(scenario.carers, scenario.clients)
    for f in sorted(TRAVEL_DIR.glob("*.json")):
        m = TravelMatrix.model_validate_json(f.read_text(encoding="utf-8"))
        if m.points == points and m.backend.startswith("osrm:"):
            return scenario, m
    raise SystemExit("no OSRM matrix for this scenario: run scripts.build_travel_matrix")


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def row(label: str, s: Solution, scenario: Scenario, m: TravelMatrix) -> str:
    ok = "yes" if not check_solution(scenario, m, s) else "**NO**"
    return (
        f"| {label} | {s.status} | {len(s.dropped)} | {s.travel_s / 60:.0f} "
        f"| {s.objective:,} | {s.wall_s:.2f} | {ok} |"
    )


def what_ifs(scenario: Scenario) -> dict[str, Scenario]:
    """Staffing changes that reuse existing locations (so the travel matrix still applies)."""
    early_idle = next(c for c in scenario.carers if c.carer_ref == "CR-0001")
    trained = early_idle.model_copy(
        update={"skills": early_idle.skills | {Skill.DEMENTIA_CARE, Skill.MEDICATION}}
    )
    late_template = next(c for c in scenario.carers if c.shift_start >= 15 * 60)
    extra = late_template.model_copy(update={"carer_ref": f"CR-{len(scenario.carers) + 1:04d}"})
    swap = tuple(trained if c.carer_ref == "CR-0001" else c for c in scenario.carers)
    return {
        "Train CR-0001 (early) in dementia care + medication": scenario.model_copy(
            update={"carers": swap}
        ),
        f"Add one late carer ({extra.carer_ref}, at {late_template.carer_ref}'s location)": (
            scenario.model_copy(update={"carers": (*scenario.carers, extra)})
        ),
        "Both": scenario.model_copy(update={"carers": (*swap, extra)}),
    }


def gantt(scenario: Scenario, s: Solution) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    carers = [r for r in s.routes if r.stops]
    for y, r in enumerate(carers):
        clock = r.departs_s
        for stop in r.stops:
            arrive = clock + stop.travel_s
            ax.barh(y, stop.travel_s / 3600, left=clock / 3600, color=TRAVEL, height=0.6)
            if stop.start_s > arrive:
                ax.barh(y, (stop.start_s - arrive) / 3600, left=arrive / 3600, color=WAIT,
                        height=0.6)  # fmt: skip
            ax.barh(y, (stop.end_s - stop.start_s) / 3600, left=stop.start_s / 3600,
                    color=SERVICE, height=0.6, edgecolor=SURFACE, linewidth=1)  # fmt: skip
            clock = stop.end_s
    ax.set_yticks(range(len(carers)), [r.carer_ref for r in carers], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(6.5, 22.5)
    ax.set_xticks(range(7, 23), [f"{h:02d}:00" for h in range(7, 23)], fontsize=8)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelcolor=INK)
    ax.set_title(
        f"Baseline rota: {s.served} visits served, {len(s.dropped)} dropped, "
        f"{s.travel_s / 60:.0f} min driving "
        f"({s.params.metaheuristic}, {s.params.time_limit_s:.0f} s)",
        loc="left", color=INK, fontsize=11, pad=24,
    )  # fmt: skip
    ax.legend(
        handles=[Patch(color=SERVICE, label="Visit"), Patch(color=TRAVEL, label="Driving"),
                 Patch(color=WAIT, label="Waiting for window")],
        frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), labelcolor=INK,
    )  # fmt: skip
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="short time limits (smoke run)")
    args = ap.parse_args()
    short, long_ = (2.0, 4.0) if args.quick else (10.0, 60.0)
    scenario, m = load()

    out = [
        "# Tier 2 baseline VRPTW (OR-Tools)",
        "",
        f"- Scenario `{scenario.name}`: {len(scenario.carers)} carers, {len(scenario.visits)} "
        f"visits; travel `{m.backend}`.",
        "- Objective = drive seconds + 1,000,000 per dropped visit (2,000,000 if time-critical).",
        "- Every solution is re-verified by `app/matching/check.py` (column *Checked*).",
        "- **Reproducibility:** search stops on a wall-clock limit, so results depend on CPU "
        "speed and load. Repeats here matched, but identical reruns of the continuity sweep "
        "changed 3 of 10 points (up to 19 min driving). Treat single numbers as ±a few %.",
        "",
        "## First-solution strategies (construction only, no local search)",
        "",
        "| Strategy | Status | Dropped | Drive (min) | Objective | Wall (s) | Checked |",
        "|---|---|---|---|---|---|---|",
    ]
    for fs in FIRST:
        p = SolverParams(time_limit_s=long_, first_solution=fs, first_solution_only=True)
        out.append(row(fs, solve(scenario, m, p), scenario, m))
    out += [
        "",
        "## Local-search metaheuristics (from PARALLEL_CHEAPEST_INSERTION)",
        "",
        "| Metaheuristic, limit | Status | Dropped | Drive (min) | Objective | Wall (s) "
        "| Checked |",
        "|---|---|---|---|---|---|---|",
    ]
    best: Solution | None = None
    for mh in META:
        for t in (short, long_):
            s = solve(scenario, m, SolverParams(time_limit_s=t, metaheuristic=mh))
            out.append(row(f"{mh}, {t:.0f} s", s, scenario, m))
            if best is None or s.objective < best.objective:
                best = s
    assert best is not None

    bound = travel_free_drop_bound(scenario)
    default = solve(scenario, m, SolverParams(time_limit_s=short))
    visits = {v.visit_id: v for v in scenario.visits}
    out += [
        "",
        "## Why visits are dropped",
        "",
        f"- **Proven lower bound:** even with *zero* travel, at least **{bound.min_dropped}** "
        f"visits cannot be served (CP-SAT, {'optimal' if bound.optimal else 'bound'}): "
        f"{', '.join(bound.unservable)}.",
        f"- **Best found:** {len(best.dropped)} dropped ({best.params.metaheuristic}, "
        f"{best.params.time_limit_s:.0f} s). The gap is the cost of travel plus heuristic "
        "sub-optimality; this bound cannot separate the two.",
        "",
        f"Dropped by the default configuration ({default.params.metaheuristic}, "
        f"{default.params.time_limit_s:.0f} s):",
        "",
        "| Visit | Window | Min | Extra skills | Eligible carers |",
        "|---|---|---|---|---|",
    ]
    for vid in default.dropped:
        v = visits[vid]
        extra = sorted(s.value for s in v.required_skills - {Skill.PERSONAL_CARE}) or ["none"]
        eligible = [c.carer_ref for c in scenario.carers if can_serve(c, v)]
        out.append(
            f"| {vid} | {hhmm(v.window_start)}-{hhmm(v.window_end)} | {v.duration} "
            f"| {', '.join(extra)} | {len(eligible)} |"
        )
    out += [
        "",
        "## Staffing what-ifs (same locations, default configuration)",
        "",
        "| Change | Dropped | Drive (min) | Travel-free bound | Checked |",
        "|---|---|---|---|---|",
        f"| None (baseline) | {len(default.dropped)} | {default.travel_s / 60:.0f} "
        f"| {bound.min_dropped} | {'yes' if not check_solution(scenario, m, default) else 'NO'} |",
    ]
    for label, sc in what_ifs(scenario).items():
        s = solve(sc, m, SolverParams(time_limit_s=short))
        b = travel_free_drop_bound(sc)
        ok = "yes" if not check_solution(sc, m, s) else "NO"
        out.append(
            f"| {label} | {len(s.dropped)} | {s.travel_s / 60:.0f} | {b.min_dropped} | {ok} |"
        )
    used = [r for r in default.routes if r.stops]
    util = [(r.service_s + r.travel_s) / ((r.stops[-1].end_s - r.departs_s) or 1) for r in used]
    out += [
        "",
        "## Default solution summary",
        "",
        f"- {default.served} visits served by {len(used)} carers; {default.travel_s / 60:.0f} min "
        f"driving ({default.travel_s / 60 / max(default.served, 1):.1f} min per visit).",
        f"- Busy share of each carer's working span (visit + driving, excluding waiting): "
        f"median {sorted(util)[len(util) // 2]:.0%}.",
        "",
        "![Baseline routes](../figures/tier2_baseline_routes.png)",
        "",
    ]
    gantt(scenario, default)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text("\n".join(out), encoding="utf-8")
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
