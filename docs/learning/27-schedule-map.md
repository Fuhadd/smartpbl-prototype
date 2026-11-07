# 27 — Schedule and map screen (Step 5.3)

## 1. What was built

**Backend**

| File | Purpose |
|---|---|
| `app/matching/explain.py` | `next_best()`: for each assignment, the **closest other qualified carer**, placed where their own route has them just before the visit (else at their start point). It records `{carer_ref, extra_travel_min, familiarity}` and is a one-swap counterfactual |
| `app/matching/models.py`, `service.py`, migration `0009` | `schedule_assignments.alternative` (JSONB, nullable). Runs are stamped with wall-clock `created_at` (see section 2) |
| `app/api/schedule.py` | `GET /schedule/latest`; `GET /schedule/tradeoff` (the published Step 2.4 sweep plus the presets); `GET /schedule/{run_id}/map` (carer starts and visit locations and windows, **only when the run's input hash matches the committed sample day**). `AssignmentOut.alternative` |
| `app/matching/presets.py` | **Continuity is now 30 min, not 45.** In the sweep, 45 is dominated by 30 |
| `scripts/sweep_continuity.py`, `data/scheduling/tradeoff.json` | The sweep now also writes JSON. This commit's JSON is taken from the published results table, so the screen shows exactly the documented numbers |
| `app/api/overview.py` | The baseline now carries `served`, so the overview can say "Serves 8 more visits than the greedy baseline" |
| Tests | `test_schedule_api.py` +4 (next best, latest, map only for the sample, presets on the Pareto front); matrix +3 routes; preset cases |

**Frontend** (`web/src/schedule/`, `pages/SchedulePage.tsx`), rebuilt from `Schedule.dc.html`:

| Piece | Design element |
|---|---|
| Header | "Schedule", the day pill (the run's date; arrows disabled, since there is one synthetic day), demo badge, Map / Timeline switch, **Re-optimise** (coordinators only) |
| `CarersPanel` | "Carers on shift" with colour dot, "5 visits · 38 min travel" and continuity %; the "Unassigned" count and dashed cards with window and reason |
| `RouteMap` | react-leaflet with OSM tiles: one coloured polyline per pinned carer, square start markers, numbered `DivIcon` visits (the selected one filled), dashed "!" unassigned markers, the legend |
| `TimelinePanel` | Hour axis, visit blocks positioned by time (gaps are travel), the selected block outlined. The Timeline view shows every carer |
| `VisitPanel` | "CL-0091 · CR-0001", "Window 09:30–10:15 · arrives 09:40", **WHY CR-0001 WAS ASSIGNED** (the stored reasons, checked), "Next best: CR-0003 · +22 min travel, new to this client" |
| `TradeoffPanel` | Travel / Balanced / Continuity; a Recharts Pareto curve with the chosen preset's dot and label; "Travel vs fastest" and "Continuity gain"; **Apply and re-optimise** |
| `model.ts` | Pure, unit-tested: carer stats, pinned colour slots, timeline scale, copy |
| States | Loading skeleton; "No rota saved yet" with "Optimise the day"; the States sheet's error *verbatim* for a failed solve ("Couldn't re-optimise the schedule … Your last saved rota is still in place"), with Try again, View saved rota and the request reference; a rate-limit variant |
| `LazySchedulePage` | The screen and its libraries load on first visit (the initial bundle stays 492 kB, not 1 MB) |

Tests: Python **412**, web **71** (16 new; Leaflet renders in jsdom, so marker counts are tested on the real map). Live smoke test on the dev database: a sample-day solve took about 20 s and returned 95 of 106 visits served. Every assignment carries an alternative, the map endpoint returned all 17 carers and 106 visits, and the overview now shows the new run against greedy.

## 2. Why this way

**The map only for the sample day.** Step 2.6 chose *not* to store the scenario with a run, only a keyed hash, so the schedule history doesn't become a second copy of where vulnerable clients live. The map needs coordinates, so the API recomputes the hash of the committed synthetic scenario and serves its locations only if they match. A caller-supplied scenario gets a clear message instead ("Runs don't store where clients live…"). In production the map would read locations from the client record under that record's own access control, not from the rota.

**Continuity = 30, not 45.** The 5.2b default put "Continuity" at 45 min. The published sweep shows 45 is **dominated**: 30 gives more familiar visits (56.4 % vs 54.3 %) for less driving (753 vs 770 min). Offering a dominated setting as a named choice would steer coordinators to a strictly worse rota. A test now asserts every preset sits on the Pareto front, so a future sweep that moves the front fails loudly.

**Preview from the sweep, then apply.** Choosing a preset moves the dot along the published curve and updates "Travel vs fastest" and "Continuity gain" *before* anything runs. That's the decision support the design asks for: see the price of continuity, then commit. A solve takes up to 20 s and is rate-limited per user, so "what would this cost?" must not need one. The saved rota is untouched until **Apply**, and the panel says so ("The saved rota uses Balanced. Nothing changes until you apply.").

**"Next best" as a labelled counterfactual.** The design asks why this carer and not another. The honest cheap answer is "the closest other qualified carer would have driven +22 min and is new to this client". It is computed once at solve time (from the same matrix), so it can't drift. It is *one-swap*: it ignores knock-on effects on both carers' days, and the UI says "before any re-planning". Re-solving with the visit forced to another carer would be exact, but would cost a solve per question.

**Three pinned routes.** Seventeen routes on one map is spaghetti, and DESIGN.md gives three route colours that differ in lightness (still readable with colour-vision deficiency). The first three carers start pinned. Clicking another replaces the *least recently chosen*, in its colour slot, so the carer you just looked at never changes colour under you. The Timeline view shows everyone.

**Straight lines between stops.** The polylines join stops in order; they show sequence, not roads. Travel times come from OSRM, so the numbers are road-accurate. Drawing road geometry would need OSRM's route service per leg (backlog).

**A bug the tests caught.** `created_at` defaults to Postgres `now()`, which is the *transaction start*. Two runs saved in one transaction get identical timestamps, and with random UUIDs "latest" was arbitrary. Runs are now stamped with wall-clock time at write.

**Code-split the map.** Leaflet and Recharts doubled the bundle. The schedule route loads them on first visit, so the overview and review queue (the coordinator's first screens) stay light.

**Deviations from the design:** carer refs instead of names (ADR-032); "Carer start" instead of "Carer home" (20 % of carers start at the office); day arrows disabled (one synthetic day).

## 3. Alternatives considered

| Option | Pros | Cons | When I'd choose it |
|---|---|---|---|
| Store the scenario (locations) with each run | Any run can be mapped | A second copy of client addresses; against data minimisation | Never in the rota table; read from the client record instead |
| Map only for the hash-matched sample (chosen) | No location data in the history | Custom scenarios aren't mappable | Prototype with one synthetic dataset |
| Counterfactual by re-solving with the visit forced to another carer | Exact cost including knock-on effects | One solve (10–20 s) per question | An "explain this choice" button for a single disputed visit |
| One-swap nearest qualified carer (chosen) | Free, stored at solve time, checkable | Approximation; ignores feasibility of the swap | Always-visible "next best" line |
| Live solve per preset preview | Exact for today's data | 20 s and a rate-limit hit per click | Small instances or a solver service with a queue |
| Precomputed sweep preview (chosen) | Instant, matches the published curve | Sample day only; 30 s per-point settings, not the API's 10 s | Decision support before committing |
| Road geometry from OSRM `route` | Realistic lines | One request per leg, more surface | Production map |

## 4. How it works

**Pareto dominance, worked example** (from `tradeoff.json`):

| w (min) | Driving | Familiar | On the front? |
|---|---|---|---|
| 30 | 753 min | 56.4 % | yes |
| 45 | 770 min | 54.3 % | **no**: 30 is better on both |

A point *dominates* another if it is at least as good on every objective and strictly better on one. The front is the set of points nothing dominates. Every sensible setting lives on it, and moving along it trades one objective for the other. "Travel vs fastest" is the move from the w=0 end: for Balanced (w=15), 716 − 597 = +119 min ≈ **+2.0 h** for 54.3 − 28.7 = **+26 pts** of continuity.

**From click to new rota:**

```mermaid
sequenceDiagram
  participant C as Coordinator
  participant UI as Schedule screen
  participant API
  participant S as OR-Tools
  C->>UI: choose "Continuity"
  UI-->>C: dot moves on the sweep curve, +2.6 h / +28 pts (no request)
  C->>UI: Apply and re-optimise
  UI->>API: POST /schedule/solve {continuity_weight_min: 30, time_limit_s: 10}
  API->>S: phase 1 coverage, phase 2 continuity (warm start)
  API->>API: explain + next best + greedy baseline, persist, audit
  API-->>UI: new run
  UI->>API: GET /schedule/{id}/map
  UI-->>C: fresh view (keyed by run id); overview invalidated
```

**Keyed remount.** The run view is rendered as `<RunView key={run.id} …>`. When a new run arrives, React throws away the old view's state (pins, selected visit) and initialises it from the new run. That replaces an effect that "reset state when the run changes", which renders twice and is easy to get wrong.

**Timeline layout.** The axis runs from the first visit's hour (floor) to the last visit's end (ceiling). A block's `left = (start − axisStart) / span` and `width = duration / span`, as percentages. A 07:00–07:30 visit on a 07:00–12:00 axis is `left 0 %, width 10 %`.

## 5. Interview questions and answers

**Q1. Why can't the map show any run, only the sample day?**
Since Step 2.6, runs store a keyed hash of their input, not the input, so the rota history isn't another copy of clients' addresses. The map endpoint recomputes the hash of the committed synthetic scenario and serves locations only on a match. With real data, locations would come from the client record under its own access control and retention, and the rota would keep references only. It's data minimisation applied to an operational screen.

**Q2. You changed the Continuity preset from 45 to 30. Why does that matter?**
The sweep shows 45 is dominated: 30 gives more familiar visits for less driving. A named button that produces a strictly worse rota is a design bug, because people trust named defaults. I added a test that every preset lies on the Pareto front, so if a new sweep moves the front, the build fails rather than silently offering a bad setting.

**Q3. How is "Next best" computed, and what are its limits?**
At solve time, for each assignment, I take every other carer qualified and on shift for the visit. I place each where their own route has them just before the visit, and compare their drive with the assigned one. The closest is stored with the difference and its familiarity. It's a one-swap counterfactual: it ignores the knock-on effects on both days, and doesn't check the other carer's later visits would still fit. The exact answer needs a re-solve with the visit forced to that carer, which I'd offer as an explicit "what if" action rather than on every visit.

**Q4. Trade-off question: why preview from a precomputed sweep instead of solving live?**
A solve takes up to 20 s and is rate-limited, so solving per click would be slow and could lock the coordinator out. The sweep shows the shape of the trade-off instantly, and Apply commits to one real solve. The cost is fidelity: the curve is the sample day at 30 s per point, while the API solves at 10 s. So the applied run can land well off the previewed point (the live Balanced run reached 47 % familiar against 54 % in the sweep), and the caption states the sweep settings. A nightly sweep at the API's settings would close that gap.

**Q5. The overview compares OR-Tools with greedy. What did live data show?**
Greedy drove 1.1 h less, but served 8 fewer visits (87 vs 95). Reporting travel alone would make the heuristic look better. The overview now says "Serves 8 more visits than the greedy baseline" next to the figure. The general lesson: compare solutions at equal coverage, or show coverage beside cost. With PBL data I'd report travel per visit served, and missed visits as the primary safety metric.

**Q6. How did you keep the screen accessible with a map and a chart?**
Every map action has a non-map path: the carers list, and timeline blocks that are real buttons with labels like "CR-0001 visit 2: CL-0091, 09:00 to 09:30". The chart is a `figure` with a sentence-length `aria-label` describing the curve and the chosen point, and the key numbers also appear as text tiles. Route colours differ in lightness, not just hue, and selection is shown by `aria-pressed` and an outline, never colour alone.

**Q7. What would you change with real PBL data and at scale?**
Real carer names and client addresses, behind object-level access (a coordinator's patch only). Self-hosted or contracted map tiles, because the public OSM servers forbid heavy use and see the viewed area. Road geometry from OSRM, and runs dated to the day they plan, with a real day switcher. Solves through a job queue with progress, instead of a 20 s request. A sweep recomputed nightly on each patch's actual day, so the preview reflects today's constraints, not the sample's.

**Q8. Why did "latest run" return the wrong run in tests, and why didn't the overview's tests catch it?**
`created_at` used the database default `now()`, which in Postgres is the transaction start time, so two runs in one transaction tie, and ordering by a random UUID breaks the tie arbitrarily. The overview tests only ever saved one run. The new test saves two in one transaction. The fix stamps wall-clock time in Python at write; an alternative is `clock_timestamp()` as the default, or a monotonic sequence column.

## 6. Learn more

**Official documentation**
- [React Leaflet: Introduction](https://react-leaflet.js.org/docs/start-introduction/): how `MapContainer` wraps Leaflet and gives child layers its map through React context.
- [Leaflet reference: DivIcon](https://leafletjs.com/reference.html#divicon): `html`, `iconSize` and `iconAnchor`, used for the numbered markers.
- [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/): attribution, no heavy use, valid Referer (it asks you *not* to set a restrictive Referrer-Policy), best-effort availability. It matters for the 5.5 demo.
- [Recharts: ReferenceDot](https://recharts.github.io/en-US/api/ReferenceDot/): highlighting the chosen point on the trade-off curve by data coordinates.

**Videos**
- *A Hands-On Introduction To Multi-Objective Optimization*, Eyal Kazin (PyCon US 2021), https://www.youtube.com/watch?v=0xDi3HwI2Y8: Pareto fronts and dominance from first principles, with Python. The same reasoning as the continuity presets. Verified on YouTube and on [pyvideo.org](https://pyvideo.org/pycon-us-2021/a-hands-on-introduction-to-multi-objective-optimization.html).

## 7. Check your understanding

In `data/scheduling/tradeoff.json`, w=20 has driving 769 min and familiar 56.4 %. Without running anything, predict: is w=20 on the Pareto front, and what happens to `test_tradeoff_presets_sit_on_the_pareto_front` if you set `Preset.CONTINUITY` to 20 in `app/matching/presets.py`?

**Expected outcome:** w=20 is **not** on the front: w=30 has the same familiar share (56.4 %) for less driving (753 < 769 min), so 30 dominates it. Setting Continuity to 20 makes the test fail on `by_w[w]["pareto"]` for 20, and `test_presets_name_the_continuity_weights` fails too (30 would no longer map to Continuity). Revert afterwards.
