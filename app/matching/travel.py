"""Travel-time matrices: OSRM road network (primary) and haversine (fallback, tests).

A matrix is square over a list of points; entry [i][j] is the time to drive from i to j.
It is *not* symmetric under OSRM: one-way streets and turn restrictions make A→B differ
from B→A.

Known limitation: OSRM's car profile uses free-flow speeds (no traffic). Birmingham at
08:00 is slower; see BACKLOG for time-dependent travel times.
"""

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from app.matching.data import Carer, Client, Location

EARTH_RADIUS_M = 6_371_000
# Fallback parameters, calibrated against OSRM on the seed-42 scenario (Step 2.2 note):
# road distance ~ DETOUR * straight line; time ~ OVERHEAD + road distance / SPEED.
# Free-flow (OSRM has no traffic): real peak-hour times are longer.
DEFAULT_DETOUR = 1.34
DEFAULT_SPEED_KMH = 42.3
DEFAULT_OVERHEAD_S = 115.0


class TravelMatrix(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: str  # e.g. "osrm:car:<data md5>" or "haversine:detour=1.34,speed=42.3,overhead=115.0"
    points: tuple[Location, ...]
    durations_s: tuple[tuple[int, ...], ...]
    distances_m: tuple[tuple[int, ...], ...]

    def index(self) -> dict[Location, int]:
        return {p: i for i, p in enumerate(self.points)}

    def seconds(self, a: Location, b: Location) -> int:
        idx = self.index()
        return self.durations_s[idx[a]][idx[b]]


def haversine_m(a: Location, b: Location) -> float:
    """Great-circle distance: the shortest path over the Earth's surface, ignoring roads."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def haversine_matrix(
    points: Sequence[Location],
    *,
    detour: float = DEFAULT_DETOUR,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    overhead_s: float = DEFAULT_OVERHEAD_S,
) -> TravelMatrix:
    """Symmetric estimate. The detour factor converts straight-line to road distance; the
    overhead stands in for junctions, lights and getting on and off the main road."""
    pts = tuple(points)
    dist: list[tuple[int, ...]] = []
    dur: list[tuple[int, ...]] = []
    for a in pts:
        road = [haversine_m(a, b) * detour for b in pts]
        dist.append(tuple(round(d) for d in road))
        dur.append(tuple(0 if d == 0 else round(overhead_s + d / (speed_kmh / 3.6)) for d in road))
    return TravelMatrix(
        backend=f"haversine:detour={detour},speed={speed_kmh},overhead={overhead_s}",
        points=pts,
        durations_s=tuple(dur),
        distances_m=tuple(dist),
    )


class OSRMError(RuntimeError):
    pass


class OSRMClient:
    """Client for OSRM's table service: all-pairs durations and distances in one request."""

    def __init__(
        self,
        base_url: str,
        *,
        data_version: str,
        profile: str = "car",
        timeout_s: float = 30,
        transport: httpx.BaseTransport | None = None,  # tests inject a mock
    ) -> None:
        self.data_version = data_version  # part of the cache key: new map data, new matrix
        self.profile = profile
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    @property
    def backend(self) -> str:
        return f"osrm:{self.profile}:{self.data_version}"

    def table(self, points: Sequence[Location]) -> TravelMatrix:
        pts = tuple(points)
        coords = ";".join(f"{p.lon},{p.lat}" for p in pts)  # OSRM wants lon,lat
        r = self._http.get(
            f"/table/v1/driving/{coords}", params={"annotations": "duration,distance"}
        )
        body = r.json()
        if r.status_code != 200 or body.get("code") != "Ok":
            raise OSRMError(f"OSRM table failed: {body.get('code')}: {body.get('message')}")
        durations, distances = body["durations"], body["distances"]
        unroutable = [
            (i, j)
            for i, row in enumerate(durations)
            for j, v in enumerate(row)
            if v is None or distances[i][j] is None
        ]
        if unroutable:
            raise OSRMError(f"no route for {len(unroutable)} pairs, e.g. {unroutable[:3]}")
        return TravelMatrix(
            backend=self.backend,
            points=pts,
            durations_s=tuple(tuple(round(v) for v in row) for row in durations),
            distances_m=tuple(tuple(round(v) for v in row) for row in distances),
        )


def cache_key(points: Sequence[Location], backend: str) -> str:
    payload = json.dumps([backend, [(p.lat, p.lon) for p in points]])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cached_matrix(
    points: Sequence[Location],
    backend: str,
    compute: Callable[[Sequence[Location]], TravelMatrix],
    cache_dir: Path,
) -> TravelMatrix:
    """Return the cached matrix for these exact points and backend, computing it once."""
    path = cache_dir / f"{cache_key(points, backend)}.json"
    if path.exists():
        return TravelMatrix.model_validate_json(path.read_text(encoding="utf-8"))
    matrix = compute(points)
    if matrix.backend != backend:
        raise ValueError(f"backend mismatch: expected {backend}, got {matrix.backend}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(matrix.model_dump_json() + "\n", encoding="utf-8")
    return matrix


def scenario_points(carers: Sequence[Carer], clients: Sequence[Client]) -> tuple[Location, ...]:
    """Unique locations in a stable order: carer starts, carer homes, client locations."""
    seen: dict[Location, None] = {}
    for c in carers:
        seen.setdefault(c.start)
        seen.setdefault(c.home)
    for c in clients:
        seen.setdefault(c.location)
    return tuple(seen)
