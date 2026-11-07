"""Build the scenario's OSRM travel matrix and calibrate the haversine fallback against it.

Usage (OSRM running: docker compose --profile osrm up -d osrm):
  uv run python -m scripts.build_travel_matrix
Writes the cached matrix to data/scheduling/travel/, docs/results/tier2_travel.md and
docs/figures/tier2_haversine_vs_osrm.png.
"""

import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.matching.data import Scenario
from app.matching.travel import (
    OSRMClient,
    TravelMatrix,
    cached_matrix,
    haversine_m,
    haversine_matrix,
    scenario_points,
)
from scripts.generate_schedule import OUT as SCENARIO_PATH

OSRM_URL = "http://127.0.0.1:5005"
MD5_FILE = Path("osrm/west-midlands-latest.osm.pbf.md5")
CACHE_DIR = Path("data/scheduling/travel")
RESULTS = Path("docs/results/tier2_travel.md")
FIGURE = Path("docs/figures/tier2_haversine_vs_osrm.png")
INK, MUTED, GRID, SURFACE, BLUE, ORANGE = (
    "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb", "#2a78d6", "#eb6834",
)  # fmt: skip


def osrm_matrix(points: tuple) -> TravelMatrix:
    version = MD5_FILE.read_text().split()[0][:12]
    client = OSRMClient(OSRM_URL, data_version=version)
    return cached_matrix(points, client.backend, client.table, CACHE_DIR)


def pairs(m: TravelMatrix) -> list[tuple[float, float, float]]:
    """(straight-line m, road m, road s) for every ordered pair i != j."""
    n = len(m.points)
    return [
        (haversine_m(m.points[i], m.points[j]), m.distances_m[i][j], m.durations_s[i][j])
        for i in range(n)
        for j in range(n)
        if i != j
    ]


def calibrate(data: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    detour = statistics.median(road / line for line, road, _ in data if line > 200)
    x = np.array([road for _, road, _ in data])
    y = np.array([sec for _, _, sec in data])
    slope, intercept = np.polyfit(x, y, 1)  # seconds = intercept + road_m * slope
    return round(detour, 2), round(3.6 / slope, 1), round(float(intercept), 0)


def errors(est: TravelMatrix, ref: TravelMatrix) -> dict[str, float]:
    n = len(ref.points)
    diffs = [
        (est.durations_s[i][j] - ref.durations_s[i][j]) / 60
        for i in range(n)
        for j in range(n)
        if i != j
    ]
    rel = [
        abs(est.durations_s[i][j] - ref.durations_s[i][j]) / ref.durations_s[i][j]
        for i in range(n)
        for j in range(n)
        if i != j and ref.durations_s[i][j] > 0
    ]
    abs_d = sorted(abs(d) for d in diffs)
    return {
        "bias_min": statistics.mean(diffs),
        "mae_min": statistics.mean(abs_d),
        "p90_abs_min": abs_d[int(0.9 * len(abs_d))],
        "max_abs_min": abs_d[-1],
        "mape": statistics.mean(rel),
    }


def asymmetry(m: TravelMatrix) -> tuple[float, float]:
    n = len(m.points)
    gaps = [
        abs(m.durations_s[i][j] - m.durations_s[j][i]) / 60
        for i in range(n)
        for j in range(i + 1, n)
    ]
    return statistics.mean(gaps), max(gaps)


def chart(data: list[tuple[float, float, float]], detour: float, speed: float, over: float) -> None:
    line_km = np.array([d[0] for d in data]) / 1000
    mins = np.array([d[2] for d in data]) / 60
    fig, ax = plt.subplots(figsize=(7, 4.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.scatter(line_km, mins, s=8, color=BLUE, alpha=0.35, linewidths=0, label="OSRM road time")
    xs = np.linspace(0, line_km.max(), 50)
    ax.plot(xs, (over + xs * 1000 * detour / (speed / 3.6)) / 60, color=ORANGE, lw=2,
            label=f"Fallback: {over:.0f} s + {detour} x distance at {speed} km/h")  # fmt: skip
    ax.plot(xs, xs / 30 * 60, color=MUTED, lw=1.5, ls="--", label="Naive: straight line at 30 km/h")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Straight-line distance (km)", color=MUTED)
    ax.set_ylabel("Drive time (min)", color=MUTED)
    ax.set_title(f"Road vs straight line — {len(data)} ordered pairs, seed-42 scenario",
                 loc="left", color=INK, fontsize=11)  # fmt: skip
    ax.legend(frameon=False, labelcolor=INK, loc="upper left")
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    scenario = Scenario.model_validate_json(SCENARIO_PATH.read_text(encoding="utf-8"))
    points = scenario_points(scenario.carers, scenario.clients)
    road = osrm_matrix(points)
    data = pairs(road)
    detour, speed, over = calibrate(data)
    fitted = haversine_matrix(points, detour=detour, speed_kmh=speed, overhead_s=over)
    naive = haversine_matrix(points, detour=1.0, speed_kmh=30.0, overhead_s=0.0)
    asym_mean, asym_max = asymmetry(road)
    chart(data, detour, speed, over)

    rows = []
    for name, m in (("Calibrated fallback", fitted), ("Naive straight line, 30 km/h", naive)):
        e = errors(m, road)
        rows.append(
            f"| {name} | {e['bias_min']:+.1f} | {e['mae_min']:.1f} | {e['p90_abs_min']:.1f} "
            f"| {e['max_abs_min']:.1f} | {e['mape']:.0%} |"
        )
    trips = [d[2] / 60 for d in data]
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(
        "\n".join(
            [
                "# Tier 2 travel times: OSRM vs straight line",
                "",
                f"- Scenario: `{scenario.name}`; {len(points)} unique points, "
                f"{len(data)} ordered pairs.",
                f"- OSRM backend: `{road.backend}` "
                "(Geofabrik West Midlands, car profile, free-flow).",
                f"- Drive times: median {statistics.median(trips):.1f} min, "
                f"max {max(trips):.1f} min.",
                f"- Road / straight-line distance (median detour factor): **{detour}**.",
                f"- Fitted time model: **{over:.0f} s + road distance at {speed} km/h**.",
                f"- Asymmetry |A→B - B→A|: mean {asym_mean:.1f} min, max {asym_max:.1f} min.",
                "",
                "| Estimator vs OSRM | Bias (min) | MAE (min) | P90 abs error (min) "
                "| Max abs error (min) | MAPE |",
                "|---|---|---|---|---|---|",
                *rows,
                "",
                "![Road vs straight line](../figures/tier2_haversine_vs_osrm.png)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(RESULTS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
