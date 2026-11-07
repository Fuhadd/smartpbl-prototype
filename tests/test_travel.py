import json
from pathlib import Path

import httpx
import pytest

from app.matching.data import Location, Scenario
from app.matching.travel import (
    OSRMClient,
    OSRMError,
    TravelMatrix,
    cache_key,
    cached_matrix,
    haversine_m,
    haversine_matrix,
    scenario_points,
)
from scripts.generate_schedule import OUT as SCENARIO_PATH

A = Location(lat=52.478, lon=-1.890)
B = Location(lat=52.488, lon=-1.890)  # 0.01 deg north
C = Location(lat=52.478, lon=-1.950)


def test_haversine_one_degree_of_latitude() -> None:
    d = haversine_m(Location(lat=52.0, lon=-1.9), Location(lat=53.0, lon=-1.9))
    assert d == pytest.approx(111_195, rel=1e-3)
    assert haversine_m(A, A) == 0


def test_haversine_matrix_formula_and_symmetry() -> None:
    m = haversine_matrix([A, B, C], detour=1.5, speed_kmh=36.0, overhead_s=100)
    straight = haversine_m(A, B)
    assert m.distances_m[0][1] == round(straight * 1.5)
    assert m.durations_s[0][1] == round(100 + straight * 1.5 / 10)  # 36 km/h = 10 m/s
    assert all(m.durations_s[i][i] == 0 for i in range(3))
    assert all(m.durations_s[i][j] == m.durations_s[j][i] for i in range(3) for j in range(3))
    assert m.seconds(A, C) == m.durations_s[0][2]


def osrm_transport(body: dict, status: int = 200, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.url)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_osrm_client_parses_table_and_sends_lon_lat() -> None:
    seen: list = []
    body = {
        "code": "Ok",
        "durations": [[0, 61.4], [75.6, 0]],
        "distances": [[0, 900.2], [1001.7, 0]],
    }
    client = OSRMClient(
        "http://osrm", data_version="abc", transport=osrm_transport(body, seen=seen)
    )
    m = client.table([A, B])
    assert "/table/v1/driving/-1.89,52.478;-1.89,52.488" in str(seen[0])
    assert "annotations=duration%2Cdistance" in str(seen[0])
    assert m.durations_s == ((0, 61), (76, 0))  # asymmetric, as real roads are
    assert m.distances_m == ((0, 900), (1002, 0))
    assert m.backend == "osrm:car:abc"


@pytest.mark.parametrize(
    ("body", "status", "match"),
    [
        ({"code": "InvalidQuery", "message": "bad coords"}, 400, "InvalidQuery"),
        (
            {"code": "Ok", "durations": [[0, None], [5, 0]], "distances": [[0, 1], [1, 0]]},
            200,
            "no route",
        ),
    ],
)
def test_osrm_errors_are_raised(body, status, match) -> None:
    client = OSRMClient("http://osrm", data_version="x", transport=osrm_transport(body, status))
    with pytest.raises(OSRMError, match=match):
        client.table([A, B])


def test_cache_computes_once_and_keys_on_points_and_backend(tmp_path: Path) -> None:
    calls = []

    def compute(points):
        calls.append(points)
        return haversine_matrix(points)

    backend = haversine_matrix([A]).backend
    first = cached_matrix([A, B], backend, compute, tmp_path)
    second = cached_matrix([A, B], backend, compute, tmp_path)
    assert first == second and len(calls) == 1
    assert cache_key([A, B], backend) != cache_key([B, A], backend)  # order matters
    assert cache_key([A, B], backend) != cache_key([A, B], "osrm:car:other")
    with pytest.raises(ValueError, match="backend mismatch"):
        cached_matrix([A, C], "osrm:car:x", compute, tmp_path)


def test_scenario_points_unique_and_stable() -> None:
    s = Scenario.model_validate_json(SCENARIO_PATH.read_text(encoding="utf-8"))
    pts = scenario_points(s.carers, s.clients)
    assert len(pts) == len(set(pts))
    assert pts[0] == s.carers[0].start
    assert all(c.location in pts for c in s.clients)


def test_committed_osrm_matrix_is_consistent() -> None:
    """The cached road matrix the solver uses: complete, zero diagonal, plausibly urban."""
    s = Scenario.model_validate_json(SCENARIO_PATH.read_text(encoding="utf-8"))
    pts = scenario_points(s.carers, s.clients)
    files = list(Path("data/scheduling/travel").glob("*.json"))
    road = next(
        m for f in files if (m := TravelMatrix.model_validate_json(f.read_text())).points == pts
    )
    assert road.backend.startswith("osrm:car:")
    n = len(pts)
    off = [road.durations_s[i][j] for i in range(n) for j in range(n) if i != j]
    assert all(road.durations_s[i][i] == 0 for i in range(n))
    assert min(off) > 0 and max(off) < 45 * 60  # inner Birmingham: under 45 min
    assert any(road.durations_s[i][j] != road.durations_s[j][i] for i in range(n) for j in range(n))
    # Calibrated fallback stays close to OSRM on average (regression guard).
    est = haversine_matrix(pts)
    mae = sum(
        abs(est.durations_s[i][j] - road.durations_s[i][j]) for i in range(n) for j in range(n)
    ) / (n * (n - 1))
    assert mae < 120  # seconds
    json.dumps(road.model_dump())  # serialisable
