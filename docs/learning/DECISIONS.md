# Architecture Decision Records

## ADR-001: Local LLM through Ollama on the host (2026-11-06)
- **Context:** Care notes are special-category health data. The dev machine is an Apple M1 Pro with 16 GB of unified memory. Docker on macOS has no Metal GPU access.
- **Decision:** Run Ollama as a host service (`brew services`). Default model `llama3.1:8b` (Q4); also pull `qwen2.5:3b` for comparison in Step 1.9.
- **Alternatives:** A hosted LLM API (data leaves PBL's control); Ollama in Docker (CPU-only on macOS); llama.cpp directly (more plumbing).
- **Consequences:** Data stays local. Docker Compose does not include the LLM, so it is documented as a prerequisite. The model choice is configurable through `SMARTPBL_LLM_MODEL`.

## ADR-002: Pin Python 3.12 (2026-11-06)
- **Context:** The system Python is 3.14. spaCy and Presidio (Step 1.3) and their compiled extensions lag new Python releases.
- **Decision:** `requires-python = ">=3.12,<3.13"` and `.python-version = 3.12`, managed by uv. This is a deviation from the "3.11+" default range, though still inside it.
- **Alternatives:** 3.14 (risk of install failure); 3.11 (works, but older).
- **Consequences:** A reproducible interpreter in dev and CI. Revisit when the NLP stack supports newer versions.

## ADR-003: Ruff through local pre-commit hooks (2026-11-06)
- **Context:** Hook and CLI ruff versions can drift when pre-commit installs its own copy.
- **Decision:** Local hooks that run `uv run ruff …` (`language: unsupported`, the pre-commit ≥4.4 name for `system`).
- **Consequences:** One ruff version, locked in `uv.lock`. The hooks need `uv` on PATH.

## ADR-004: Extraction schema design (2026-11-06)
- **Context:** The LLM output must be machine-checkable, auditable and safe to show coordinators.
- **Decision:** A single Pydantic `Extraction` model is used as both the Ollama `format` constraint and the validator. 7-category closed taxonomy. 3-level severity, each level tied to an action. Evidence is a verbatim quote (not offsets) placed before severity and confidence. `extra="forbid"`, all fields required. Negated risks are omitted.
- **Alternatives:** JSON mode only; free text then parse; character offsets; 5-level severity.
- **Consequences:** Output always parses, but correctness is not guaranteed (a sanity check missed a fall), so grounding, review and evaluation are needed. Self-reported confidence is used only for ranking and routing. The taxonomy and severity definitions need validation with PBL managers before use with real data.

## ADR-005: Template-based synthetic care notes with held-out phrases (2026-11-06)
- **Context:** Tier 1 needs labelled notes for tuning and evaluation. No real data can be used. Labels must be trustworthy, and evaluating an LLM on LLM-labelled data is circular.
- **Decision:** A seeded template generator (seed 42). 80 dev / 40 test, generated as separate balanced streams (exactly 8 flags per category in test). 14 phrases are test-only to prevent phrase leakage. Messiness is applied before evidence is extracted. Synthetic PII uses ranges that can't be real (Ofcom drama numbers, NHS 999 range, ZZ postcodes). Committed files are checked against the generator by a test.
- **Alternatives:** LLM-generated notes (circular, noisy labels); random category sampling plus searching for a passing seed (rejected as tuning data to pass its own check); a single shared phrase pool (leakage).
- **Consequences:** Labels are exact and reproducible. Narrow vocabulary favours keyword rules, so results compare methods rather than estimate real accuracy. See DATA_CARD.md for biases.

## ADR-006: PII redaction with Presidio, UK recognisers and an entity allowlist (2026-11-06)
- **Context:** Notes contain names, phones, NHS numbers and addresses. Data minimisation (UK GDPR Art. 5(1)(c)) means the LLM should see only clinical content. spaCy and Presidio defaults missed UK formats, lowercase names and word-like names, and would mask times.
- **Decision:** Presidio with spaCy `en_core_web_lg` 3.8.0, plus custom recognisers: UK postcode, NHS-like (no checksum), UK phone, street address, titled name, kinship name (case-sensitive name group). Allowlist of 7 entity types (no DATE_TIME). Score threshold 0.35. Typed placeholders. Output is the `RedactedText` type, which the LLM layer must require. Optional `known_names` deny-list for gazetteer names from the care record.
- **Alternatives:** regex only; spaCy trf; LLM-based redaction (rejected: raw PII would go into the model); case-insensitive kinship matching (rejected: 100% recall but test evidence preservation drops to 83.9%).
- **Consequences:** Test PII recall 98.3%, evidence preserved 96.4%. Lowercase word-like family names remain a gap unless `known_names` is supplied. Grounding (1.6) must check against the redacted text. Adds a ~400 MB model download (CI must cache it).

## ADR-007: Rules baseline with the same output schema, tuned on dev only (2026-11-06)
- **Context:** LLM metrics need something to compare against. The author of the rules also wrote the template phrases (including test-only ones).
- **Decision:** Regex lexicon per category with per-pattern severity, context requirements, NegEx-style pre-trigger negation (5 tokens, scope ends at but/however, number "no" excluded), and a time-comparison rule. Returns `Extraction`. Run on redacted text. v0 from generic vocabulary; v1 changes only from logged dev errors; test closed until 1.9. Typos deliberately not handled.
- **Alternatives:** spaCy Matcher + negspaCy; fuzzy matching; TF-IDF + logistic regression (needs labelled data).
- **Consequences:** Dev micro F1 0.986 (optimistic: tuned). Authorship bias is acknowledged; the real fix is separate roles or real notes. Constant confidence (0.7) carries no information for routing.

## ADR-008: LLM extraction via Ollama structured outputs, versioned prompts, derived fields in code (2026-11-06)
- **Context:** Extraction must be valid, reproducible, auditable and impossible to run on unredacted text.
- **Decision:** `httpx` client to Ollama `/api/chat` with `format` = Pydantic JSON schema, temperature 0, seed 42, connect/read timeouts 5/60 s. `extract()` accepts only `RedactedText`; validates; one retry with error feedback; then `ExtractionFailedError` (goes to human review). Prompts are versioned files with a SHA-256 recorded; the model is recorded by digest. `follow_up_required` is recomputed from severities and overrides are logged. Prompt v2 is the default after a dev-only v1 → v2 iteration; iteration stopped to avoid overfitting dev.
- **Alternatives:** Ollama SDK; Instructor/Outlines; JSON mode only; two-step reason-then-format; many dev few-shot examples.
- **Consequences:** Dev: 160/160 valid first try; v2 micro F1 0.938, severity agreement 0.827. Self-reported confidence is uninformative (86% at 1.0), so routing can't use it. Median latency 5.7 s/note on an M1 Pro.

## ADR-009: Tiered evidence grounding (threshold 90) and policy-based review routing with a baseline safety net (2026-11-06)
- **Context:** LLM evidence must be verifiable; risky or uncertain flags need meaningful human review (UK GDPR Art. 22A as amended by the DUAA 2025). LLM confidence is uninformative.
- **Decision:** Ground against the redacted text: exact → normalised → fuzzy (`partial_ratio` ≥ 90, ≥ 3 words, span snapped to words) → ungrounded. Route to review on high severity, safeguarding, fuzzy, ungrounded, confidence < 0.7, baseline-only category, or extraction failure. Nothing is dropped.
- **Alternatives:** exact only; embedding similarity; NLI entailment; confidence-only routing.
- **Consequences:** Dev: 0 ungrounded; 59% of notes reviewed / 10.1% escape without the safety net; 64% / 0% with it (optimistic: rules tuned on dev). Grounding checks presence, not meaning (negation and category errors pass). The threshold must be recalibrated on real data.

## ADR-010: Postgres persistence, append-only audit log via trigger, HMAC input hashes (2026-11-06)
- **Context:** Every AI decision must be traceable (input, model, prompt, output, actor, time) without the audit log becoming a second copy of health data. Audit rows must be unchangeable.
- **Decision:** SQLAlchemy 2.x + Alembic. Tables: care_notes, extractions, risk_flags (mutable review_status), audit_events. A hand-written trigger rejects UPDATE/DELETE (row) and TRUNCATE (statement). Enums are VARCHAR + CHECK (`create_constraint=True`). Input hash = **HMAC-SHA256** with a secret key (deviation from the spec's plain SHA-256, to prevent dictionary attacks on short notes); `hash_alg` stored. `audit_events.note_id` is not a foreign key. Model work happens before the transaction; LLM failure degrades to baseline flags plus review. Postgres on 127.0.0.1:5442.
- **Alternatives:** plain SHA-256; DB role permissions only; hash chain; external WORM/ledger; event sourcing.
- **Consequences:** Tamper-resistant against the app, but not against the table owner or a superuser (DISABLE TRIGGER/DROP work). Production needs separate roles, plus a hash chain or external store. The HMAC key must be managed as a secret.

## ADR-011: Review API with per-flag locked decisions, re-grounded edits and a stored diff (2026-11-07)
- **Context:** Coordinators must approve, edit or reject flags. Decisions must be attributable, race-free, and recorded with what changed, without putting personal data into the permanent audit log.
- **Decision:**
  - **Routes:** `POST /notes`, `GET /notes/{id}`, `GET /review/queue`, `POST /review/{flag_id}` and `GET /audit/{note_id}`. Routers are thin over the `app/nlp/review.py` service.
  - **Each decision is one transaction:** `SELECT … FOR UPDATE` on the flag, then update the flag, insert a `review_decisions` row (before, after, field diff, comment) and append a `review_decision` audit event (the diff and `has_comment` only).
  - **Which flags can be reviewed:** decided flags return 409, and auto-accepted flags can be overridden.
  - **Edits are re-grounded:** edited evidence must be grounded in the redacted note. The note's matched span is what gets stored.
  - **Redacted text only:** responses use explicit Pydantic models, and `raw_text` is never returned.
  - **Ingest:** `POST /notes` is synchronous. It checks for duplicates before calling the LLM and releases its connection during the call.
  - **Reviewer identity** comes from the `X-Reviewer` header until Step 4.1. This is a declared stand-in, not access control.
- **Alternatives:** optimistic concurrency (ETag/version column); diff only in the audit log; event-sourced flags; async ingest with 202 and a queue.
- **Consequences:**
  - Lost updates are prevented. This is tested by asserting the lock appears in the emitted SQL.
  - Reviewer corrections become queryable labels.
  - Gaps: notes whose LLM extraction failed and the baseline found nothing stay in the queue with no flag to act on, because there is no note-level sign-off yet. Reviewers can't add a flag the system missed. Decisions can't be corrected. The queue is sorted in Python.

## ADR-012: Build cadence: steps run back-to-back, with a review at each tier milestone (2026-11-07)
- **Context:** Before this, every step stopped for explicit approval. With the 15 Nov deadline for Tiers 1–2, waiting between steps cost more time than it saved.
- **Decision:** Steps run consecutively. Each step still meets the full definition of done (code, tests, lint, learning note, ADR/glossary/interview updates, commit). Work pauses only at tier milestones, when a decision is genuinely the learner's, or when blocked. Default choices are recorded here.
- **Alternatives:** keep stopping after every step; batch several steps into one commit.
- **Consequences:** Faster progress. Review moves to tier boundaries, so each tier summary must list every learning note to read. Per-step commits keep the history reviewable.

## ADR-013: Evaluation protocol, and keeping llama3.1:8b as the extraction model (2026-11-07)
- **Context:** Tier 1 needs an honest comparison of the LLM and the rules on data neither was tuned on, small enough to run on a laptop.
- **Decision:**
  - **Scoring:** per-note, per-category matching. Failed extractions count as no flags.
  - **Reported:** micro and macro P/R/F1 with 1000-resample bootstrap CIs, a 2000-resample paired bootstrap against the rules, and union recall. Also schema validity, grounding, severity agreement, latency, robustness slices, confusion by evidence overlap, and deployed-pipeline escape and workload.
  - **Test split opened once** (`--final`), with no tuning afterwards.
  - **Prediction files committed** for reproducibility.
- **Alternatives:** span-level matching; scikit-learn multilabel metrics; LLM-as-judge; regenerating a larger synthetic test set.
- **Consequences:**
  - **Results (test, n = 40):** llama F1 0.906 / recall 0.857; rules 0.860 / 0.768; qwen 0.651 / 0.500.
  - **The difference is not significant:** the paired bootstrap gives llama vs rules F1 +0.046 (−0.034 to +0.141).
  - **The deployed pipeline** reviews 50% of notes, with a 7.1% escape rate and 0 high-severity escapes.
  - **The rules overfit dev,** dropping from 0.986 to 0.860 F1.
  - **llama3.1:8b stays the default. qwen2.5:3b is rejected** for now: it reaches only about 50% recall on both splits.

## ADR-014: Scheduling data model and synthetic scenario simplifications (2026-11-07)
- **Context:** Tier 2 needs a reproducible, care-shaped scheduling instance with skills, shifts, arrival windows and preferences, without any real location data.
- **Decision:**
  - **Time:** one day, in integer minutes from midnight.
  - **Hard constraints are explicit fields:** skills, shift window, arrival window, duration.
  - **Preferences are separate soft fields:** `preferred_carers`, `recent_carers`.
  - **Generator:** seeded, with clients in three Gaussian patches inside an inner-Birmingham box, coordinates rounded to 3 decimal places, early and late continuous shifts, ±30-minute windows (±15 for time-critical medication), and preferences drawn only from carers qualified for all the client's needs.
  - **Validation:** the generator refuses to write a scenario where a visit's skill combination has no carer on a covering shift.
  - **Defaults chosen without asking:** everyone drives, there are no split shifts or breaks, and there are no double-up calls.
- **Alternatives:** Solomon/Gehring–Homberger benchmarks; home-health-care literature instances; anonymised real rotas (needs a DPIA).
- **Consequences:**
  - 17 carers, 40 clients, 106 visits.
  - The morning peak is about 90% loaded once travel is counted, so dropped visits are likely in 2.3.
  - Per-skill coverage proved insufficient (skill-mix gap with 7 early carers), so validation is mandatory.
  - Results from one synthetic day are illustrative only.

## ADR-015: Self-hosted OSRM (MLD) for travel times, with a calibrated haversine fallback (2026-11-07)
- **Context:** The solver needs directed drive times between all scenario points. Client locations are personal data, and experiments need reproducibility.
- **Decision:**
  - **OSRM:** `ghcr.io/project-osrm/osrm-backend:v26.4.0`, the newest tag published with arm64 support (later releases have no image tag). It runs on the Geofabrik West Midlands extract with the car profile and the MLD pipeline, as an opt-in Compose profile on `127.0.0.1:5005`.
  - **Matrices:** fetched with one `/table` call and cached by a hash of the ordered points and the backend, which includes the map MD5. The scenario's matrix is committed.
  - **Fallback:** `115 s + 1.34 × straight line at 42.3 km/h`, fitted to 3,306 OSRM pairs (MAE 1.3 min, bias 0).
- **Alternatives:** Google, Mapbox or HERE matrix APIs; GraphHopper or Valhalla; uncalibrated haversine.
- **Consequences:**
  - Times are free-flow, with no traffic, so they are optimistic at peak hours.
  - The matrix is asymmetric (up to 3.2 min).
  - Tests and the solver run without Docker.
  - Changing map data invalidates the cache by design.

## ADR-016: Baseline VRPTW model and solver configuration (2026-11-07)
- **Context:** Assign 106 visits to 17 carers respecting skills, shifts and arrival windows, on a day that is over capacity.
- **Decision:**
  - **Model:** OR-Tools routing library with one vehicle per carer. Routes start at the carer's start location and end at a zero-cost dummy node (open routes; the trip home is not counted).
  - **Time:** a dimension in seconds (transit = service + drive; up to 4 h waiting allowed).
  - **Hard constraints:** windows and shifts as limits on the time dimension; eligibility through each visit's vehicle-variable domain.
  - **Optional visits:** penalty 1,000,000, doubled for time-critical visits. This exceeds the maximum possible driving, about 446,000 s, so visits are dropped only when forced.
  - **Search defaults:** PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH, 10 s, chosen from measured results on this instance.
  - **Checking:** every solution is verified by an independent checker, with a CP-SAT travel-free lower bound on drops.
  - **Not costed yet:** waiting time.
- **Alternatives:** CP-SAT circuit model; MIP; ALNS, PyVRP or HGS; closed routes (return home).
- **Consequences:**
  - 12 drops at 10 s and 11 at 60 s, against a proven minimum of 2.
  - Drops come from a morning skill-mix bottleneck and an evening bed-time peak.
  - Staffing what-ifs reduce drops to 7.
  - Idle gaps of 1–2.5 h are visible mid-shift.
  - The choice of tabu over GLS rests on one instance.
  - OR-Tools 9.15's SWIG binding rejects lists in `SetAllowedVehiclesForIndex`, so `VehicleVar().SetValues` is used instead.

## ADR-017: Continuity as a weighted per-visit penalty, swept with coverage fixed (2026-11-07)
- **Context:** Continuity of care (NICE QS123 statement 3) conflicts with travel. The provider needs the trade-off made visible, not hidden in one solution.
- **Decision:**
  - **Penalty per visit:** w for a new carer, w/2 for a recent carer, 0 for a preferred carer. It's applied as a per-carer arc cost on arrival, with w in seconds of driving.
  - **Guard:** drop penalty > maximum travel + visits × w, so continuity never costs a visit.
  - **Sweep:** w = 0–60 minutes with coverage fixed lexicographically (a continuity-blind solve, then the same 94 visits each time), warm-started from the reference routes.
  - **Front:** non-dominated over (driving, familiar visits, drops).
  - **Framing:** a CP-SAT travel-free continuity ceiling.
- **Alternatives:** ε-constraint; hard preferred-only constraint; fixed teams then routing.
- **Consequences:**
  - The front runs from 29% familiar at 597 min to 56% at 753 min, against a proven ceiling of 81%.
  - The first 7 points cost only 7 min a day; the middle of the curve costs about 6.5 min per extra familiar visit.
  - At w > 30 the search degrades. Weights are best chosen per client group and checked on more days.
  - `solve()` gains an `initial=` warm start.

## ADR-018: Greedy baseline and a multi-day evaluation protocol for scheduling (2026-11-07)
- **Context:** The optimiser has to beat what a coordinator would do by hand, on days it wasn't tuned on.
- **Decision:**
  - **Greedy:** take visits in window order (time-critical first on ties) and give each to the nearest eligible carer who can arrive in time. It returns the same `Solution` type, checked by the same checker.
  - **Comparison:** greedy vs OR-Tools w=0 vs OR-Tools w=15 two-phase (warm-started from w=0), on the first 5 seeds from 42 upwards that pass validation (45–47 were rejected), using OSRM matrices.
  - **Metrics:** unassigned, time-critical unassigned, driving, familiar carer %, utilisation, runtime.
  - `Solution.params` is now optional.
- **Alternatives:** greedy with a continuity tie-break; regret insertion; the historical rota (needs real data).
- **Consequences:**

  | | Unassigned | Time-critical unassigned | Driving | Familiar carer |
  |---|---|---|---|---|
  | Greedy | 25.2 | 5.4/day | 663 min | 22% |
  | OR-Tools w=0 | 17.8 | 0 | 596 min | 29% |
  | OR-Tools w=15 two-phase | 17.0 | 0 | 687 min | 56% |

  - **Utilisation** is about 50–55% for every method, because peaks bind.
  - **The generator rejected 3 of 8 seeds,** so the valid days are a filtered sample.

## ADR-019: Schedule API with fact-based explanations, minimised persistence, and audited runs (2026-11-07)
- **Context:** Coordinators need plans they can trust and challenge. Runs must be traceable without keeping copies of client locations.
- **Decision:**
  - **Endpoints:** `POST /schedule/solve` (scenario or committed sample; time limit ≤ 30 s; weight 0–60 min; two-phase if weight > 0) and `GET /schedule/{id}`.
  - **Explanations:** reasons recomputed from scenario and matrix (skills, drive and origin, arrival vs window, familiarity, other eligible carers); dropped visits classed as `no_eligible_carer` or `eligible_carers_busy`.
  - **Persistence:** `schedule_runs` and `schedule_assignments`. The scenario itself is not stored, only its name, seed and an HMAC of its canonical JSON (skill sets serialise sorted).
  - **Audit:** a `schedule_solved` event (parameters, seed, objective, OR-Tools version, backend, run id), written once with a pre-generated run UUID. The CHECK swap is hand-written in migration 0003.
  - **Validation:** integrity problems return 422; unservable visits are planned around and reported.
  - **Timing rule:** earliest service within each window; the carer departs as late as still reaches the first visit.
- **Alternatives:** counterfactual "why not X?" explanations; objective decomposition; storing full scenarios; async jobs.
- **Consequences:**
  - Live on the sample day: w=0 drops 12 with 30.9% familiar at 629 min; w=15 drops 11 with 47.4% familiar at 700 min.
  - Requests block for up to 2 × the time limit, so a queue plus rate limiting are needed in Tier 4.
  - The audit table's `note_id` is note-specific; a generic subject id is deferred to 4.2.

## ADR-020: Synthetic workforce from Tier 2 carer-days with a known attrition mechanism (2026-11-07)
- **Context:** Tier 3 needs attrition data. No real HR data exists, and the brief asks for features derived from Tier 2. A synthetic label risks circular "findings".
- **Decision:**
  - **Calibration:** `scripts/calibrate_workforce.py` solves the 5 Tier 2 evaluation days (OSRM, w=15 two-phase) once and commits 85 carer-days. This keeps solver noise out of the generator.
  - **Working conditions:** per carer, a home round (p=0.6) or another same-rota day for each of 13 weeks of shifts. Driving, unpaid gaps, split-day share (single gap ≥ 90 min), visits and familiarity are averages over those shifts.
  - **Employment features** are stated assumptions: age band, tenure, zero-hours (about 37%), shifts per week, short-notice changes.
  - **Label:** an explicit ground-truth logistic model (steps, hinge, an interaction, 4 null features) plus an unobserved factor U ~ N(0,1). The intercept is solved to give a 30% leaver rate (an assumption between sector-wide ~25% and older domiciliary ~39% figures).
  - **Oracle:** `p_oracle = E_U[sigmoid(·)]` by Gauss–Hermite quadrature, kept in a separate file that is never a model input.
  - **Protected attribute:** `age_band` is stored for auditing only, excluded from `FEATURES` (enforced by a test), with no direct effect.
  - **Size and split:** n = 1,000, stratified 80/20 split with `random_state=42`, fixed before looking.
  - **Dependencies:** adds scikit-learn and pandas.
- **Alternatives:** independent random features; a public HR dataset (IBM sample: fictional, not care-sector); a survival-time generator with censoring.
- **Consequences:**
  - 29.8% leavers. Oracle AUC is 0.726 overall; 0.754 even with no U, because of Bernoulli noise.
  - **The test split is easy:** the oracle reaches 0.795 on it, the 97th percentile of 200 random splits (95% range 0.645–0.795). It was kept; Step 3.2 uses CV as the main estimate and reports test scores next to the oracle on the same rows.
  - Leaver rates differ by age (47% for 18–24 vs 23% for 55+) through tenure and contract alone, which sets up the proxy-discrimination audit in 3.3.
  - Results show the pipeline recovers a known mechanism, nothing about real carers.
