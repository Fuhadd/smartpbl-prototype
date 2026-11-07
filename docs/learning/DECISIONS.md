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
  - **Label:** an explicit ground-truth logistic model (steps, hinge, an interaction, 5 null features: `weekly_paid_hours` was missing from the list until Step 3.3) plus an unobserved factor U ~ N(0,1). The intercept is solved to give a 30% leaver rate (an assumption between sector-wide ~25% and older domiciliary ~39% figures).
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

## ADR-021: Nested CV protocol and model set for attrition (2026-11-07)
- **Context:** 800 training carers (238 leavers), a 200-row test split known to be easy (ADR-020), and an exploratory look at HGB settings on the evaluation folds before the protocol existed.
- **Decision:**
  - **Candidates:** standardised logistic regression; the same with `class_weight="balanced"` (kept as a teaching contrast, not for use); `HistGradientBoostingClassifier` (150 iterations).
  - **Tuning:** each candidate is a `GridSearchCV` (3-fold inner, scored on log loss), so hyperparameters are chosen inside each outer training fold: LR `C ∈ {0.01, 0.1, 1}`; HGB depth {2, 3} × learning rate {0.03, 0.1} × min leaf {20, 50}.
  - **Main estimate:** 5×5 repeated stratified CV, with the oracle and a constant base-rate predictor scored on the same folds, plus paired per-fold comparisons.
  - **Test:** the test split is used once, with 2,000-resample bootstrap CIs, quoted next to the oracle.
  - **Metrics:** ROC-AUC, PR-AUC as average precision, Brier, precision in the top 10%/20% of risk, and error vs the true probability.
- **Alternatives:** non-nested CV (optimistic after the exploratory peek); a single train/validation split (too noisy at 800 rows); SMOTE/oversampling (distorts probabilities like reweighting); post-hoc calibration (unnecessary when the unweighted models are already calibrated in the mean).
- **Consequences:**
  - **CV:** HGB 0.675 ROC-AUC / 0.538 AP / 0.188 Brier vs LR 0.655 / 0.483 / 0.196 (HGB better in 18/25, 20/25 and 22/25 folds); oracle 0.709 / 0.556 / 0.181.
  - **Balanced weights:** same ranking, Brier 0.232 (worse in 25/25 folds), mean prediction 48% vs a 30% base rate.
  - **Test** cannot separate the models (LR 0.772, HGB 0.759, overlapping CIs).
  - HGB chooses depth 2 and learning rate 0.03 in most folds: shallow trees, which can still represent the steps and pairwise interaction.
  - About 2 minutes per run; deterministic (fixed seeds, no early stopping below 10k rows).

## ADR-022: SHAP path-dependent explanations, a ground-truth check, and use-restricted fairness (2026-11-07)
- **Context:** Coordinators need per-carer reasons; managers and auditors need global behaviour and a fairness view. Age is excluded from the inputs but correlates with tenure and contract type.
- **Decision:**
  - **Explainer:** SHAP `TreeExplainer` on the re-tuned HGB in log-odds, `feature_perturbation="tree_path_dependent"`. Interventional mode was tried first and **rejected**: in shap 0.54.1 its values fail additivity for `HistGradientBoostingClassifier` (up to 0.51 log-odds, growing with the number of trees; exact for `GradientBoostingClassifier`). The additivity check stays on, with a regression test.
  - **Reasons:** top contributions in plain units, a lever flag, and a support action only when risk is raised.
  - **Ground-truth check (synthetic only):** exact Shapley values of the generator's log-odds per carer (one- and two-feature terms), compared with model SHAP.
  - **Fairness:** an age audit on 1,000 out-of-sample predictions (selection rate in the top 20%, ratio to the most-flagged band, calibration by band). Fairness is controlled through **restricted use** in the model card, not by altering the model.
  - **Correction:** `weekly_paid_hours` added to `NULL_FEATURES` (5 null features).
- **Alternatives:** interventional SHAP; permutation importance; LR coefficients; counterfactual explanations; fairness-constrained training (e.g. equalising selection rates by age, which would deliberately under-serve young carers who really are at higher risk).
- **Consequences:**
  - Global ranking vs truth: Spearman 0.81. Per-carer r ≥ 0.90 for tenure, contract and changes.
  - **Split shifts are under-credited** (r 0.13), because their signal is carried by the correlated gaps.
  - A null feature appears in the top-risk carer's explanation.
  - Selection ratio for 55+ vs 18–24 is 0.17, carried by tenure.
  - Path-dependent attributions follow data correlations. Explanations are presented as factors to discuss, not causes.

## ADR-023: Workforce API serving out-of-sample scores, retrained at start-up, with audited reads (2026-11-07)
- **Context:** Coordinators and managers need ranked risk and per-carer explanations. Scores about employees are sensitive, and the model card promises audited, supportive use.
- **Decision:**
  - **Endpoints:** `GET /workforce/risk` (rank, risk, `support_priority` for the top 20%, top 3 factors; paging; `priority_only`) and `GET /workforce/{carer_ref}/explanation` (12 SHAP factors in log-odds, `baseline_risk` vs `average_risk`, suggested support for provider levers adding ≥ 0.1 log-odds, caveats).
  - **Served workforce:** the 200 held-out carers, so every score is out of sample.
  - **Model loading:** retrained on first use from committed data (`lru_cache`, ~4 s), not unpickled. The version is a digest of the data, estimator, grid, and scikit-learn and SHAP versions.
  - **Audit:** every read writes `workforce_risk_viewed` / `workforce_explanation_viewed` (actor, carer refs, model version), committed with the request. Migration 0004 is hand-written.
  - **Minimal properties:** explicit response models, never the label or age band (tested).
  - **No score table:** scores are recomputed, not stored.
- **Alternatives:** pickle/joblib artefacts; a `skops` + registry setup; a batch score table; a separate scoring service.
- **Consequences:**
  - Cold start of about 4 s per worker process.
  - GET requests write audit rows.
  - Identity is still the prototype `X-Reviewer` header until 4.1, so these endpoints are **not access-controlled yet**.
  - The audit `note_id` column is unused here (generic subject deferred to 4.2).

## ADR-024: Tier 5 becomes a React coordinator dashboard plus a Flutter carer app (2026-11-07)
- **Context:** The project plan was changed by the project owner (noticed at the Tier 3 milestone). It replaces the Flutter coordinator app with a web dashboard for coordinators and a separate carer-facing app.
- **Decision:**
  - **5.1–5.4:** a React coordinator dashboard (Vite + TypeScript, React Router, TanStack Query, a typed client generated from the FastAPI OpenAPI schema; react-leaflet with OSM tiles; role-aware routes).
  - **5.5:** a live demo deployment in "demo mode" with seeded, precomputed results, because the LLM runs locally.
  - **5.6:** a Flutter carer app (mobile + web PWA via `flutter build web --wasm`, deployed to Firebase Hosting in demo mode) for today's visits and care-note submission.
  - **5.7:** demo links and per-role credentials in the README and on the login screen.
- **Alternatives:** the original single Flutter coordinator app (one codebase, but coordinators work at desks, where a web dashboard fits better); a Flutter web dashboard (one language, but a weaker ecosystem for data-dense tables and charts).
- **Consequences:**
  - The README roadmap is updated.
  - Tier 4's CORS and auth design must serve two browser origins.
  - The OpenAPI schema becomes a contract: the response models from Tiers 1–3 (spans, reasons, SHAP factors, use notice) are what the clients consume.
  - Demo mode needs seeded data and no Ollama dependency.

## ADR-025: JWT access tokens, rotating DB-tracked refresh tokens, and a permission table (2026-11-07)
- **Context:** Steps 1.8–3.4 identified users by a client-supplied `X-Reviewer` header, which is not access control. Reviewer decisions, solver runs and workforce-risk reads need a verified identity and least-privilege roles (coordinator, manager, carer). Two client types are coming in Tier 5 (a React dashboard and a Flutter carer app).
- **Decision:**
  - **Tokens:** HS256 JWT access tokens (15 min) and JWT refresh tokens (7 days). Decoding pins the algorithm and requires `exp, iat, iss, aud, sub, jti, type`; a `type` claim prevents a refresh token from being used as an access token.
  - **Refresh state:** each refresh `jti` is stored (never the token), in a family per login. Tokens are single use (rotation), and reuse of a rotated token revokes the family (RFC 9700 §4.14.2). The row is locked during rotation.
  - **Authorisation:** the user is reloaded from the DB on every request, and the current role and `is_active` decide. The role claim in the token is for client UI only.
  - **Policy:** routes declare a `Permission`, and one role → permissions table maps them. Managers oversee (audit, workforce risk, read-only operations); coordinators act (review decisions, solver, notes); carers create notes only.
  - **Enforcement:** router-level authentication runs before endpoint dependencies. A guard test (OpenAPI security plus a `require(...)` on every non-public route), an independently written route × role matrix and a coverage test keep the policy honest.
  - **Passwords:** Argon2id via pwdlib defaults (m = 64 MiB, t = 3, p = 4). The same 401 for unknown user, wrong password and disabled account; a dummy hash for timing parity. Accounts are created by a CLI, with no self-registration.
- **Alternatives:** opaque server-side sessions (equally defensible here; not what the plan specified); an external OIDC IdP such as Entra ID (preferred for production at PBL); RS256 with JWKS (only worth it with several verifying services); role checks inline in routes (spreads the policy across files).
- **Consequences:**
  - Logout and rotation can't revoke an access token already issued, but disabling an account takes effect on the next request because of the DB reload.
  - Tokens are returned in the JSON body. A browser cookie variant (`httpOnly` refresh cookie plus CSRF) is decided with CORS in 4.3.
  - No login rate limiting yet (4.3), and the default signing secret is not yet refused outside local development (4.3).
  - Login and permission-denied events are not audited yet (4.2).
  - Expired refresh rows are not yet purged.
  - Carers can't read notes back until object-level checks exist (Tier 5).
  - FastAPI 0.162 includes routers lazily, so route introspection uses the OpenAPI schema plus a `ROUTERS` tuple, not `app.routes`.

## ADR-026: Unified audit via ASGI middleware, request-id correlation and generic subjects (2026-11-07)
- **Context:** Auditing relied on each endpoint calling `record()`. AI decisions and workforce views were covered, but reads of notes, the queue, schedules and the audit trail were not, and nor were logins and refusals. Events were tied to `note_id` only, and nothing linked a model decision to the user whose request caused it.
- **Decision:**
  - **Access layer:** a pure ASGI `AuditMiddleware` writes one `api_request` row per routed call: actor, method, route template, status, duration, and a subject from path parameters via `SUBJECT_PARAMS`. `/health`, docs and unmatched paths are skipped.
  - **Fail closed:** responses are buffered; if the row can't be written, GET and HEAD return 500 without the body. Writes return their real outcome (their domain events committed atomically with the change) and log the failure.
  - **Correlation:** a per-request `RequestAudit` object in a context variable carries `request_id` (also sent as `X-Request-ID`), the authenticated actor and any attempted login username. `record()` stamps every event with the request id.
  - **Schema (migration 0006):** `subject_type`/`subject_id` (indexed) and `request_id` (indexed); new events `api_request`, `review_queue_viewed` and `refresh_token_reuse_detected`. No backfill (append-only); downgrade refuses if new events exist.
  - **Actor = decision-maker:** pipeline events stay `system:pipeline`; the submitter is on the correlated request row.
  - **Minimisation:** the attempted username is HMAC-hashed; no query strings, raw paths or free text.
  - **Note trail:** `GET /audit/{note_id}` returns the note's events, the requests that caused them, direct reads, and queue views that showed it.
- **Alternatives:** explicit calls only (forgettable); `BaseHTTPMiddleware` (breaks context-variable propagation, less control); DB triggers or `pgaudit` (no app user or model context; a complement for superuser activity); an external SIEM only (infrastructure; personal data leaves the boundary).
- **Consequences:**
  - One extra insert per request.
  - Whole responses are buffered (fine for JSON, not for future streaming).
  - Older rows have no subject or request id.
  - Tests and middleware share `dependency_overrides[get_session]`.
  - Retention, partitioning and alerting are backlog items.

## ADR-027: Security hardening from the OWASP API Top 10 review (2026-11-07)
- **Context:** Step 4.3 reviewed the API against the OWASP API Security Top 10 (2023). The review found three defects: a zero-carer scenario aborted the process inside OR-Tools; an overlong `note_id` caused a 500 after an LLM call; 422 responses echoed submitted note text. Rate limiting, secrets handling and CORS were not yet implemented.
- **Decision:**
  - **Secure defaults:** outside `environment=local`, refuse to start with the public JWT or audit-key defaults, a JWT key under 32 bytes, or `*` CORS (all problems reported together). Docs and the OpenAPI schema only in local.
  - **Rate limits:** an in-memory sliding-window log per process. Login 20/min per IP and 5/min per username, before Argon2; notes 30/min and solves 3/min per user; 429 with `Retry-After`; refused requests not counted.
  - **Resource bounds:** a 1 MB body limit (declared and chunked); note ids `^[A-Za-z0-9_.-]{1,50}$`; scenario caps (60 carers, 200 clients, 400 visits, 10 carer refs per client, at least one carer); the solver itself refuses zero carers.
  - **Headers:** the OWASP REST set (`nosniff`, `no-store`, CSP `default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options`, `Referrer-Policy`), plus HSTS outside local.
  - **CORS:** an explicit origin list, `GET`/`POST`, `Authorization`/`Content-Type`, no credentials, exposing `X-Request-ID` and `Retry-After`.
  - **Token storage (supersedes the cookie plan in note 20):** bearer tokens in the `Authorization` header only. The dashboard keeps them in memory; mobile uses secure storage. No cookies, so no CSRF surface.
  - **Validation errors:** returned without `input` or `ctx`.
  - **Tooling:** ruff flake8-bandit (`S`) with reasoned suppressions; `pip-audit` (clean on 2026-11-07).
- **Alternatives:** `slowapi`; Redis token buckets; gateway-only limits; an `httpOnly` refresh cookie plus CSRF tokens; a backend-for-frontend.
- **Consequences:**
  - Limits are per process and reset on restart (documented; Redis in the backlog).
  - A dashboard reload requires a new login.
  - An attacker can lock a known username out of login for a minute at a time.
  - Unauthenticated bodies up to 1 MB are read before auth.
  - TLS, `--no-server-header` and proxy-header configuration are deferred to Step 4.4.

## ADR-028: Multi-stage uv image, Compose with a migration job, and four-job CI (2026-11-07)
- **Context:** Tier 4.4 needs the API, database and OSRM runnable as one stack, with Ollama documented as a host service, and lint plus tests on every push.
- **Decision:**
  - **Image:** two stages. uv 0.11.16 builds `/app/.venv` with `--locked --no-dev --no-install-project` in a lockfile-keyed layer; the `python:3.12.13-slim` runtime holds only the venv and source. It runs as uid 10001, with a `HEALTHCHECK` on `/health`, and uvicorn with `--no-server-header --proxy-headers` (`FORWARDED_ALLOW_IPS`).
  - **Compose:** `db` (healthy) → `migrate` (one-shot `alembic upgrade head`) → `api` (`service_completed_successfully`). The API has a read-only root filesystem with tmpfs `/tmp`, `cap_drop: [ALL]`, `no-new-privileges`, and is bound to 127.0.0.1. Secrets come from `.env` (optional `env_file`), with container addresses overriding host ones.
  - **Ollama:** stays on the host (macOS containers can't use Metal), reached at `host.docker.internal` (`host-gateway` for Linux).
  - **CI (GitHub Actions):** four parallel jobs, `lint` (dev group only), `test` (Postgres 16 service, `SMARTPBL_REQUIRE_DB=1`), `audit` (pip-audit 2.10.1) and `docker` (build, gha cache, no push). `permissions: contents: read`, `persist-credentials: false`, `UV_LOCKED=1`, actions pinned to commit SHAs verified via the GitHub API.
- **Alternatives:** a single-stage image; distroless or Chainguard bases; migrations at API start-up; containerised Ollama (CPU-only on macOS); tag-pinned actions; one serial CI job.
- **Consequences:**
  - The image is 2.3 GB, mostly ML dependencies and the spaCy `lg` model.
  - CI never exercises the real LLM (`-m ollama` stays opt-in).
  - The amd64 Linux test run is rehearsed locally under emulation, but CI itself first runs on push.
  - No registry push, signing or image scanning yet (backlog).

## ADR-029: Coordinators may read workforce risk and the audit log (2026-11-07)
- **Context:** The Tier 5 designs (`docs/design/`) put Workforce and Audit in the coordinator's rail and a "Carers at elevated risk" card on the coordinator overview, and the access-denied copy says workforce risk "is visible to coordinators and care managers". ADR-025 had restricted both permissions to managers. The attrition model card had always named coordinators and managers as primary users, so ADR-025 was stricter than the documented intended use.
- **Decision (project owner, 2026-11-07):** follow the design. Coordinators gain `workforce.read` and `audit.read`. Carers still get neither.
- **Alternatives:** keep manager-only and hide those design elements from coordinators; grant audit only.
- **Consequences:**
  - The permission table, the independent route × role matrix and `SECURITY.md` are updated.
  - Every workforce-risk and audit read stays audited, and the supportive-use notice and model-card restrictions still apply.
  - The "authorisation before expensive dependencies" test now uses a carer.

## ADR-030: React dashboard architecture: generated typed client, in-memory auth, server-authoritative guards (2026-11-07)
- **Context:** Step 5.1 builds the coordinator dashboard shell to the design spec (`docs/design/DESIGN.md`, `Login.dc.html`, `States.dc.html`, the shell of `Main.dc.html`) on top of the Tier 4 API.
- **Decision:**
  - **Stack:** `web/` with Vite 8, React 19, TypeScript 5.9 (strict; TypeScript 7 conflicts with `openapi-typescript`'s peer range), Tailwind v4 and shadcn/ui (Button, Badge, Input, Label, Card, Skeleton, ToggleGroup) with design variants added, React Router 8 (data mode) and TanStack Query 5.
  - **Contract:** `scripts/export_openapi.py` writes `web/openapi.json` and `openapi-typescript` generates `schema.d.ts`. pytest fails on schema drift; CI regenerates the types and fails on any diff. The runtime client is `openapi-fetch`.
  - **Auth:** tokens in memory (ADR-027); one `authFetch` adds the bearer token, single-flight refresh on 401 and one retry. A failed refresh ends the session.
  - **Guards:** permissions come from `/auth/me`. The rail is filtered, `Guarded` renders the access-denied state, and the page's API read is still sent so the server refuses and audits it. The "recorded" copy appears only after the 403.
  - **Tokens and fonts:** design tokens as CSS variables mapped to Tailwind and shadcn names; Inter self-hosted (no Google Fonts request); light-only (`dark:` bound to an unused class).
  - **Demo accounts:** the design's exact credentials, seeded by `scripts/seed_demo.py` in `local`/`demo` environments only. `users.display_name` added (migration 0007).
  - **Design gaps filled:** sign-in error and rate-limit messages, and a sign-out menu on the user chip.
- **Alternatives:** orval or openapi-generator hooks; hand-written types; Next.js or React Router framework mode with a backend-for-frontend; storing tokens in localStorage.
- **Consequences:**
  - A reload signs the user out.
  - Overview panels and the review, schedule, workforce and audit screens are labelled stand-ins until Steps 5.2 to 5.4.
  - Search and notifications render but do nothing yet.
  - The shadcn `cn` package (5 days old) was replaced by the local `clsx` + `tailwind-merge` helper.
  - In development, StrictMode sends a denied page's probe twice (two audit rows); production sends one.

## ADR-031: Note-level atomic review decisions and escalation; Step 5.2 split (2026-11-07)
- **Context:** `Review.dc.html` decides a whole extraction (Approve, Reject, Escalate to care manager) and shows an approval route with "Care manager sign-off". The API decided single flags and had no escalation. Step 5.2 also had to cover the overview panels and the audit screen, each needing new endpoints.
- **Decision:**
  - **Endpoint:** `POST /review/notes/{note_id}` (`review.decide`) applies decisions for exactly the note's pending flags in one transaction (note row locked; each flag through `review_flag`, so per-flag diffs and audit events are kept). Any invalid edit rolls back the set.
  - **Escalation:** `escalate: true` sets `care_notes.escalated_at` / `escalated_by` and appends `review_escalated`; it is refused (409) unless a kept flag is high severity (DESIGN.md interaction rule). Migration 0008.
  - **Queue items** include `carer_ref`.
  - **Frontend:** the review screen rebuilt from the design. Highlights come from the stored grounding offsets. The title is built from the top flag and the visit time, not the model's summary. Escalate is shown only while a kept flag is high.
  - **Split:** Step 5.2 becomes **5.2a** (review screen, this ADR) and **5.2b** (overview panels and the audit log screen).
- **Alternatives:** per-flag calls from the browser; a partial-success batch endpoint; escalation as an audit event only; using the LLM summary as the title.
- **Consequences:**
  - There is no care-manager sign-off screen yet (not in the designs; backlog).
  - The design's per-category protocol text exists only as the falls placeholder.
  - Four category colours were chosen outside the design.
  - The confidence threshold is mirrored as a frontend constant.

## ADR-032: Overview summary endpoint, audit timeline projection, greedy comparison and relative risk bands (2026-11-07)
- **Context:** Step 5.2b builds `Main.dc.html` and `Audit.dc.html`. The overview needs data from four tables and the workforce model. The audit screen shows one line per meaningful event, while the log stores fine-grained rows. Two design elements had no backing data: "vs manual" (there is no manual rota) and "Carers at elevated risk" (no band definition).
- **Decision (defaults confirmed by the project owner, 2026-11-07):**
  - **`GET /overview`** (`review.queue.read`): one snapshot for all panels, reusing `queue_items()`. Sections the role can't read are null. Quoted note evidence and the named carer are audited like the queue and the risk list.
  - **Schedule comparison:** "vs greedy baseline". Every solve also runs the Step 2.5 greedy heuristic on the same day and matrix and stores `metrics.baseline`. Older runs show no comparison. Presets: Travel 0, Balanced 15, Continuity 45, otherwise Custom (Continuity changed to 30 by ADR-033).
  - **Risk bands:** elevated = support-priority group (top 20 %), moderate = above the team average, low = the rest. Returned as `band` on workforce responses.
  - **Audit timeline:** a read-time projection (`app/audit/timeline.py`). Anchor and companion event types are grouped by request id and note id, each entry lists its raw row ids, pagination is keyset over anchor ids, and the copy is built server-side so screen and CSV agree. Successful requests, "viewed" rows and the rules baseline aren't shown (still in the log and in `GET /audit/{note_id}`). 403 refusals and token-reuse alerts are shown.
  - **`GET /audit/summary`** (today in Europe/London) and **`GET /audit/export`** (CSV, at most 5000 entries, formula cells neutralised per OWASP).
  - **Frontend deviations:** a WAI-ARIA disclosure row instead of shadcn Collapsible (a `<div>` can't wrap table rows), CSS bars instead of Recharts, an `hmac-sha256:` fingerprint prefix (the design says `sha256:`; the stored hash is keyed), and `CL-`/`WF-` refs instead of the design's names.
- **Alternatives:** panels calling existing endpoints; a materialised summary table; writing display rows into the log; OFFSET pagination; "vs manual" with an invented figure; fixed probability cut-offs for bands.
- **Consequences:**
  - Solves take a few milliseconds longer (greedy).
  - The first overview after start-up waits about 5 s for the workforce model to train.
  - "Today's schedule" is the latest saved run, not one dated today.
  - Search runs `ILIKE` with sub-selects (no index), fine at prototype volume.
  - The design's "Workforce risk scores · 31 carers scored" row has no event (scoring isn't audited as an AI output yet; backlog).

## ADR-033: Schedule screen: hash-gated map, sweep preview, next-best counterfactual, Continuity = 30 (2026-11-07)
- **Context:** Step 5.3 builds `Schedule.dc.html`: a route map, a timeline, "why this carer" with "Next best", and an "Optimise for" trade-off panel. Runs don't store locations (Step 2.6). There was no "next best" data and no machine-readable sweep. ADR-032's Continuity preset (45) turned out to be dominated in the published sweep.
- **Decision:**
  - **Map:** `GET /schedule/{run_id}/map` serves locations only when the run's input HMAC matches the committed synthetic sample; any other run gets 404 with an explanation. Locations are not added to runs.
  - **Next best:** computed at solve time by `next_best()` (the closest other qualified carer, placed where their own route has them) and stored as `schedule_assignments.alternative` (migration 0009). It is labelled in the UI as before any re-planning.
  - **Trade-off:** `GET /schedule/tradeoff` serves `data/scheduling/tradeoff.json` (taken from the published Step 2.4 table; future sweeps write it directly). Choosing a preset previews the sweep point and Apply runs one solve.
  - **Presets:** Travel 0, Balanced 15, **Continuity 30** (supersedes 45 in ADR-032). A test asserts every preset is on the Pareto front.
  - **`GET /schedule/latest`**; runs stamped with wall-clock `created_at` (the `now()` default is transaction-scoped and tied).
  - **Frontend:** react-leaflet 5 with OSM tiles, Recharts 3, three pinned route colours with least-recently-chosen replacement, timeline view of all carers, code-split route. The design's day arrows are disabled (one synthetic day), and "Carer home" became "Carer start".
  - **Overview:** the greedy baseline also reports `served`, and the panel says "Serves N more visits than the greedy baseline".
- **Alternatives:** store scenarios with runs; exact counterfactual by forced re-solve; a live solve per preview; road geometry from OSRM `route`; keep 45.
- **Consequences:**
  - Only the sample day is mappable.
  - The preview uses 30 s-per-point sweep results, while the API solves at 10 s, so applied runs can sit off the curve.
  - Public OSM tiles are fine for a demo, not production (usage policy; the viewed area is visible to the tile server).
  - The OSM policy asks web clients not to set a restrictive Referrer-Policy, which constrains the 5.5 hosting headers.

## ADR-034: Workforce screen: SHAP in percentage points, team-median comparisons, actions only from support levers (2026-11-07)
- **Context:** Step 5.4 builds `Workforce.dc.html`. The design shows percentage-point SHAP bars ("Team baseline 43% → Joy 68%"), 4-week trends on signal tiles, carer names, and "Plan" buttons. The model is explained in log-odds (ADR-022), the synthetic workforce is one snapshot with no names, and no planning backend exists.
- **Decision:**
  - **Points:** the server converts log-odds SHAP to percentage points by proportional rescaling, ppⱼ = 100·(p − p₀)·φⱼ/Σφ (local slope p₀(1 − p₀) if Σφ ≈ 0). The rows add up exactly to the score, keep signs and ranking, and are exposed as `FactorOut.points`.
  - **Team comparison:** `FactorOut.team_value` is the team median, or the share answering yes for yes/no features. Signal tiles show it in place of trends.
  - **Chart:** the top 6 factors plus one "N other factors" row, so the chart still adds up. It's a custom grid, no library, with screen-reader text per row.
  - **Actions:** cards come only from `suggested_support`, the API's levers adding ≥ 0.1 log-odds. The check-in card appears only for the Elevated band. "Open in schedule" shows for rota-set factors and only with `schedule.read`. No "Plan" buttons.
  - **Identity:** carers are shown by ref with an icon avatar (as on the schedule screen). The header line comes from tenure, contract and shifts.
  - **Model card:** a disclosure panel fed by the API (name, version, notice, caveats).
  - **Routing and bundles:** `/workforce` redirects to rank 1. The screen is lazy-loaded (`LazyPages.tsx`), keeping the initial bundle at 492 kB.
- **Alternatives:** raw log-odds; per-factor σ(base + φ) − σ(base) (doesn't add up); sequential attribution (order-dependent); SHAP on probability (interventional mode broken for HGB, ADR-022); invented trends; a Recharts bar chart.
- **Consequences:**
  - The percentage split is a convention, which the footnote and note 28 state; exact log-odds stay in the API.
  - Trend, planning and per-carer access features are deferred (backlog).
  - The list loads all 200 carers, so one view's audit event lists 200 refs.

## ADR-035: Carer app API: `/me` routes, object-level note checks, need-to-know handover, urgent concern (2026-11-07)
- **Context:** Step 5.6 adds the carer app (Visits, VisitDetail, Note, Submitted designs). Carers previously had only `note.create`, with no link between a login and a scheduling identity, and could submit a note with any `carer_ref`, a latent BOLA issue.
- **Decision:**
  - **Identity link:** `users.carer_ref` is nullable and unique (migration 0010); `seed_demo` links Joy to CR-0001. New permission `visits.read.own`, for carers only.
  - **Reads:** `GET /me/visits` and `GET /me/visits/{visit_id}` derive the carer from the token. Another carer's visit gets a 404 (no existence oracle).
  - **Handover:** the detail includes the client's last 3 notes (redacted, rejected flags hidden), only for clients on today's rota, each read audited as `client_notes_viewed` (subject type `visit` added in migration 0011).
  - **Writes:** for carers, `POST /notes` requires their own `carer_ref`, a `visit_id` on their current rota, and that visit's `client_ref` (403 otherwise). Coordinators are unchanged.
  - **Note fields:** `visit_id`, `urgent` and `tasks_done` (optional). `urgent` forces `review_required`, sorts first and counts as high priority. A flag-less urgent note is acknowledged through the existing note decision.
  - **"Done":** a note by this carer for the visit, created on the run's local calendar day (avoids comparing API and database clocks).
  - **Hosting the carer app:** Vercel (the user's choice for frontends), not the Firebase Hosting named in CLAUDE.md; the user deploys.
- **Alternatives:** `/carers/{ref}/visits` with per-handler checks; Postgres row-level security; a policy engine; a separate visit-notes table; no handover notes.
- **Consequences:**
  - "Today" is the latest run, since the prototype has one synthetic day.
  - Visit details and locations exist only for the sample day.
  - Neon was migrated to 0010 from a laptop whose `.env` pointed at it. 0011 must still be applied there (`alembic upgrade head` against Neon) before deploying this API image.

## ADR-036: Flutter carer app: web PWA with --wasm, repository-faked tests, memory tokens, idempotent submit (2026-11-07)
- **Context:** Step 5.6b builds the carer screens (CarerLogin, Visits, VisitDetail, Note, Submitted) in Flutter, to be tried in a phone browser and installable, on the same API as the dashboard.
- **Decision:**
  - **Stack:** Flutter 3.35 with Riverpod 3 (global `retry: null`: failures show "Try again" rather than silent retries), GoRouter (session-driven redirect, hash URLs), Dio with a plain `Interceptor` (single-flight refresh, one retry; not `QueuedInterceptor`, which can deadlock on a failed retry).
  - **Session:** tokens in memory only (ADR-027); non-carer accounts are refused at sign-in.
  - **Testing:** screens read a `Repository` through `repositoryProvider`, which widget tests override with a fake; the interceptor is tested with a fake HTTP adapter; tests load the bundled Inter font.
  - **Build:** `flutter build web --wasm` (skwasm, with automatic dart2js + CanvasKit fallback). The PWA manifest and icons are generated from the design's "S" tile. `web/vercel.json` sets COOP/COEP for multi-threaded rendering. Inter is bundled.
  - **Behaviour:** the next visit is the first without a note (not by clock). The note id is created once per note, and a 409 on retry counts as sent.
  - **Design trims:** no Rota or My notes tabs, notifications bell, "Good to know" or visit counts (no backend yet). The demo badge replaces the bell. "Call office" uses Ofcom drama number 0121 496 0000.
  - **CI:** a `mobile` job runs format, analyze (infos fatal), test and the wasm build. flutter-action is pinned to a commit SHA.
- **Alternatives:** a React mobile view; native-only store apps; a JS-only Flutter build; mocking Dio in widget tests; persisting tokens in web storage.
- **Consequences:**
  - First load is about 2.4 MB gzipped on the Wasm path (about 3.6 MB on the JS fallback), against 0.15 MB for the dashboard. The service worker caches the app after the first load.
  - A reload signs the carer out.
  - There is no offline mode yet.
