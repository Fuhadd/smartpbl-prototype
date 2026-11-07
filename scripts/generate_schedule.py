"""Generate a synthetic one-day scheduling scenario (Tier 2).

Usage: uv run python -m scripts.generate_schedule [--seed 42]
Writes data/scheduling/scenario.json and prints load statistics for the data card.

Everything is synthetic: references only (CR-0001, CL-0001), no names or addresses.
Coordinates are random points in a Birmingham bounding box, rounded to 3 decimal places
(~100 m), so no point identifies a real home.
"""

import argparse
import random
from collections import Counter
from pathlib import Path

from app.matching.data import Carer, Client, Location, Scenario, Skill, Visit, validate_scenario

SEED = 42
OUT = Path("data/scheduling/scenario.json")

# Inner Birmingham, roughly Handsworth-Small Heath-Selly Oak-Erdington.
LAT_MIN, LAT_MAX = 52.42, 52.54
LON_MIN, LON_MAX = -1.98, -1.78
OFFICE = Location(lat=52.478, lon=-1.890)  # synthetic office, city-centre area
N_PATCHES = 3  # providers organise rounds into geographic patches
PATCH_SD = 0.018  # ~2 km

N_CLIENTS = 40
SHIFTS = {"early": (7 * 60, 14 * 60 + 30), "late": (15 * 60, 22 * 60)}
N_CARERS = {"early": 10, "late": 7}

CARER_SKILL_RATE = {
    Skill.MEDICATION: 0.7,
    Skill.MANUAL_HANDLING: 0.45,
    Skill.DEMENTIA_CARE: 0.4,
    Skill.CATHETER_CARE: 0.25,
}
MIN_PER_SHIFT_SKILL = 2  # guarantee coverage: at least 2 carers per skill per shift
CLIENT_NEED_RATE = {
    Skill.MEDICATION: 0.6,
    Skill.MANUAL_HANDLING: 0.2,
    Skill.DEMENTIA_CARE: 0.25,
    Skill.CATHETER_CARE: 0.1,
}
TIME_CRITICAL_RATE = 0.15  # of clients with medication needs

# Care packages: which calls a client gets, and how often each package occurs.
PACKAGES = {
    ("morning", "lunch", "tea", "bed"): 0.40,
    ("morning", "lunch", "bed"): 0.20,
    ("morning", "bed"): 0.25,
    ("morning",): 0.15,
}
# Slot: (preferred-time range, duration choices, skills that apply at this call).
SLOTS = {
    "morning": (
        (7 * 60 + 30, 9 * 60 + 30),
        (30, 45, 60),
        {Skill.MEDICATION, Skill.MANUAL_HANDLING, Skill.DEMENTIA_CARE, Skill.CATHETER_CARE},
    ),
    "lunch": ((12 * 60, 13 * 60), (30,), {Skill.MEDICATION, Skill.DEMENTIA_CARE}),
    "tea": ((16 * 60 + 30, 17 * 60 + 30), (30,), {Skill.MEDICATION, Skill.DEMENTIA_CARE}),
    "bed": (
        (19 * 60 + 30, 21 * 60),
        (30, 45),
        {Skill.MEDICATION, Skill.MANUAL_HANDLING, Skill.DEMENTIA_CARE, Skill.CATHETER_CARE},
    ),
}
WINDOW_HALF = 30  # minutes either side of the preferred time
CRITICAL_HALF = 15


def _point(rng: random.Random, centre: Location, sd: float) -> Location:
    lat = min(max(rng.gauss(centre.lat, sd), LAT_MIN), LAT_MAX)
    lon = min(max(rng.gauss(centre.lon, sd * 1.6), LON_MIN), LON_MAX)  # 1° lon ≈ 0.61° lat here
    return Location(lat=round(lat, 3), lon=round(lon, 3))


def _carers(rng: random.Random, patches: list[Location]) -> list[Carer]:
    plan = [(shift, i) for shift, n in N_CARERS.items() for i in range(n)]
    skills: list[set[Skill]] = [
        {Skill.PERSONAL_CARE} | {s for s, p in CARER_SKILL_RATE.items() if rng.random() < p}
        for _ in plan
    ]
    for shift in N_CARERS:
        idx = [i for i, (sh, _) in enumerate(plan) if sh == shift]
        for skill in CARER_SKILL_RATE:
            while sum(skill in skills[i] for i in idx) < MIN_PER_SHIFT_SKILL:
                skills[rng.choice([i for i in idx if skill not in skills[i]])].add(skill)
    carers = []
    for n, ((shift, _), sk) in enumerate(zip(plan, skills, strict=True), 1):
        home = _point(rng, rng.choice(patches), PATCH_SD * 2)
        start, end = SHIFTS[shift]
        carers.append(
            Carer(
                carer_ref=f"CR-{n:04d}",
                skills=frozenset(sk),
                shift_start=start,
                shift_end=end,
                home=home,
                start=OFFICE if rng.random() < 0.2 else home,
            )
        )
    return carers


def _client_and_visits(
    rng: random.Random, n: int, patch: Location, carers: list[Carer], next_visit: int
) -> tuple[Client, list[Visit]]:
    needs = frozenset(
        {Skill.PERSONAL_CARE} | {s for s, p in CLIENT_NEED_RATE.items() if rng.random() < p}
    )
    critical = Skill.MEDICATION in needs and rng.random() < TIME_CRITICAL_RATE
    package = rng.choices(list(PACKAGES), weights=list(PACKAGES.values()))[0]

    # Preferences only among carers qualified for everything the client needs.
    able = [c for c in carers if needs <= c.skills]
    rng.shuffle(able)
    preferred: list[str] = []
    if rng.random() > 0.15:  # 15% state no preference
        for lo, hi in ((0, 15 * 60), (15 * 60, 24 * 60)):  # one early, one late if possible
            pick = next((c for c in able if lo <= c.shift_start < hi), None)
            if pick and rng.random() < 0.8:
                preferred.append(pick.carer_ref)
    recent = sorted(set(preferred) | {c.carer_ref for c in able[: rng.randint(1, 3)]})

    client = Client(
        client_ref=f"CL-{n:04d}",
        location=_point(rng, patch, PATCH_SD),
        needs=needs,
        preferred_carers=tuple(preferred),
        recent_carers=tuple(recent),
    )
    visits = []
    for slot in package:
        (lo, hi), durations, slot_skills = SLOTS[slot]
        preferred_time = rng.randrange(lo, hi + 1, 5)
        is_critical = critical and Skill.MEDICATION in slot_skills
        half = CRITICAL_HALF if is_critical else WINDOW_HALF
        visits.append(
            Visit(
                visit_id=f"V-{next_visit + len(visits):04d}",
                client_ref=client.client_ref,
                window_start=preferred_time - half,
                window_end=preferred_time + half,
                duration=rng.choice(durations),
                required_skills=frozenset({Skill.PERSONAL_CARE} | (needs & slot_skills)),
                time_critical=is_critical,
            )
        )
    return client, visits


def generate(seed: int = SEED) -> Scenario:
    rng = random.Random(seed)
    centre = Location(lat=(LAT_MIN + LAT_MAX) / 2, lon=(LON_MIN + LON_MAX) / 2)
    patches = [_point(rng, centre, 0.03) for _ in range(N_PATCHES)]
    carers = _carers(rng, patches)
    clients, visits = [], []
    for n in range(1, N_CLIENTS + 1):
        client, vs = _client_and_visits(rng, n, rng.choice(patches), carers, len(visits) + 1)
        clients.append(client)
        visits.extend(vs)
    visits.sort(key=lambda v: (v.window_start, v.visit_id))
    return Scenario(
        name=f"birmingham-day-seed{seed}",
        seed=seed,
        carers=tuple(carers),
        clients=tuple(clients),
        visits=tuple(visits),
    )


def stats(s: Scenario) -> dict[str, object]:
    by_shift: dict[str, dict[str, int]] = {}
    for name, (start, end) in SHIFTS.items():
        carers = [c for c in s.carers if c.shift_start == start]
        demand = sum(v.duration for v in s.visits if start <= v.window_start < end)
        capacity = len(carers) * (end - start)
        by_shift[name] = {"carers": len(carers), "service_min": demand, "capacity_min": capacity}
    return {
        "carers": len(s.carers),
        "clients": len(s.clients),
        "visits": len(s.visits),
        "time_critical_visits": sum(v.time_critical for v in s.visits),
        "carer_skills": dict(Counter(sk.value for c in s.carers for sk in c.skills)),
        "visit_skills": dict(Counter(sk.value for v in s.visits for sk in v.required_skills)),
        "clients_with_preference": sum(bool(c.preferred_carers) for c in s.clients),
        "carers_starting_at_office": sum(c.start == OFFICE for c in s.carers),
        "by_shift": by_shift,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    scenario = generate(args.seed)
    problems = validate_scenario(scenario)
    if problems:
        raise SystemExit("invalid scenario:\n" + "\n".join(problems))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(scenario.model_dump_json(indent=1) + "\n", encoding="utf-8")
    for k, v in stats(scenario).items():
        print(f"{k}: {v}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
