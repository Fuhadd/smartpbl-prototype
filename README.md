# SMARTPBL Prototype

[![CI](https://github.com/Fuhadd/smartpbl-prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/Fuhadd/smartpbl-prototype/actions/workflows/ci.yml)

A working prototype of **SMARTPBL**, an AI platform for a domiciliary (home) care provider. I built it for a KTP Associate application (AI Software Engineer, Birmingham City University × PBL Care).

> **Independent prototype, all data synthetic.** This is not affiliated with or endorsed by PBL Care. No real people, clients or PBL Care records are used. Results on synthetic data do not show real-world performance.

## The problem

A home-care provider sends carers to hundreds of short visits a day. Three things go wrong at scale:

1. **Risks hide in free-text notes.** A fall, refused medication or a safeguarding hint is buried in hundreds of notes a day, and coordinators can't read them all.
2. **Rotas trade travel against continuity of care.** Hand-built rotas waste driving time or send strangers to clients who need familiar faces, and late or missed visits follow.
3. **Carers leave.** Turnover in adult social care is high, and the working conditions behind it (short-notice changes, unpaid gaps, long drives) are set by the rota.

SMARTPBL addresses each with an AI component, behind a secure API with human review and an audit trail:

```mermaid
flowchart LR
  subgraph Clients
    D[Coordinator dashboard<br/>React · TypeScript]
    C[Carer app<br/>Flutter · web PWA]
  end
  subgraph API[FastAPI · JWT roles · audit middleware · rate limits]
    N1[Care-notes NLP<br/>redact → local LLM + rules<br/>→ ground → route]
    N2[Carer matching<br/>OR-Tools VRPTW<br/>+ continuity weight]
    N3[Attrition risk<br/>gradient boosting + SHAP<br/>supportive use only]
    R[Human review<br/>approve · edit · reject · escalate]
  end
  C -->|care note| N1
  N1 --> R
  D --> R
  D --> N2
  D --> N3
  N2 -->|working conditions| N3
  N2 -->|today's visits| C
  API --> DB[(PostgreSQL<br/>append-only audit log)]
  N1 -.->|redacted text only| O[Ollama<br/>llama3.1:8b, local]
```

### SMARTPBL innovations mapped to this prototype

| Innovation | Implemented as | Where |
|---|---|---|
| NLP on care notes that flags risks | PII redaction (Presidio + UK recognisers) → local LLM with a JSON-schema contract → evidence grounding → routing to human review; rules baseline as a safety net | `app/nlp/`, `POST /notes`, dashboard **Review**, Tier 1 |
| Human oversight and audit of AI decisions | Note-level approve/edit/reject with reviewer diffs, escalation, append-only audit log with keyed input hashes, audit timeline and CSV export | `app/nlp/review.py`, `app/audit/`, dashboard **Audit log** |
| Intelligent carer matching and routing | VRP with time windows, skills and shifts (OR-Tools), road travel times (OSRM), explained assignments with a next-best alternative | `app/matching/`, `POST /schedule/solve`, dashboard **Schedule** |
| Continuity of care as an explicit trade-off | Continuity weight in minutes of driving, Pareto sweep, Travel / Balanced / Continuity presets on the front | `app/matching/continuity.py`, `presets.py`, Tier 2 |
| Workforce attrition prediction | Gradient boosting on rota-derived working conditions, calibrated probabilities, SHAP explanations, model card, age audit | `app/workforce/`, dashboard **Workforce**, Tier 3 |
| Carer-facing digital tools | Today's visits, a handover of recent notes, and care notes with an urgent-concern switch, all object-level authorised | `app/api/me.py`, `mobile/`, Tier 5 |
| Secure, compliant platform | JWT roles with least privilege, OWASP API Top 10 review, data minimisation, local inference, CI | `app/auth/`, [`docs/SECURITY.md`](docs/SECURITY.md), Tier 4 |

### Results at a glance

All results are on synthetic data, with seed 42. The tier sections below have the full tables and caveats.

| Tier | Headline | Evaluated on |
|---|---|---|
| 1 · Care-notes NLP | LLM recall **0.857**, F1 **0.906** (rules: 0.768 / 0.860). The deployed pipeline let **0 of 19** high-severity flags escape, and 100% of evidence was grounded | Held-out test split: 40 notes, 56 gold flags |
| 2 · Carer matching | vs a greedy heuristic: unassigned visits **17.0 vs 25.2**, time-critical misses **0 vs 5.4**, familiar carers **56% vs 22%** | 5 synthetic days, about 106 visits each |
| 3 · Attrition | Gradient boosting ROC-AUC **0.675**, PR-AUC **0.538** against an oracle ceiling of 0.709 / 0.556; top-10% precision 69% (base rate 30%) | Nested 5×5 CV on 800 synthetic carers |
| 4 · Production layer | Role × route permission matrix tested for every endpoint; 10 OWASP API risks reviewed | 436 API tests in CI |
| 5 · Apps | Live dashboard and carer app; screens rebuilt from the design files | 87 dashboard and 22 Flutter tests |

## Try the demo

| | Link | Sign in as |
|---|---|---|
| **Coordinator dashboard (web)** | https://tend-swart.vercel.app | `hannah@demo.smartpbl` / `demo-coordinator` (coordinator) or `sam@demo.smartpbl` / `demo-manager` (care manager) |
| **Carer app (open in a phone browser)** | https://tend-carer.vercel.app | `joy@demo.smartpbl` / `demo-carer` |

Both sign-in screens show these accounts. The passwords are public on purpose: the seed script refuses to create them outside `local` or `demo` environments.

**Try this:**
1. As Hannah, open **Schedule** and click **Optimise the day**. This takes about 20 s and saves a rota.
2. As Joy in the carer app, see the day's visits, open one, write a note, and raise an urgent concern.
3. Back as Hannah, the note is at the top of **Review**. Approve or acknowledge it, then find the decision in the **Audit log**.

The carer app installs to the home screen: use Add to Home Screen in Safari or Chrome.

**What to expect:**
- **Slow first load:** the first request after a quiet spell takes 5–10 s while the database and API wake up from scale-to-zero.
- **No AI extraction on the hosted demo:** the LLM runs locally (Ollama), so notes written there are saved but not extracted. The AI flags already in the review queue were produced locally on the same synthetic notes.
- **Synthetic data:** every name, client, carer and note is synthetic.

## Status

- [x] Step 0: setup
- [x] Tier 1: care-notes NLP (schemas, synthetic data, PII redaction, rules baseline, LLM extraction, grounding + routing, persistence + audit, API + human review, evaluation)
- [x] Tier 2: carer matching (scheduling data, OSRM travel matrix, OR-Tools VRPTW, continuity trade-off, greedy comparison, schedule API)
- [x] Tier 3: attrition prediction (synthetic workforce from Tier 2 schedules, LR vs gradient boosting with nested CV, SHAP explanations checked against ground truth, age audit, model card, workforce API)
- [x] Tier 4: production layer: 4.1 JWT auth with refresh rotation and role-based permissions; 4.2 unified audit (middleware access log, request-id correlation, fail-closed reads); 4.3 OWASP API Top 10 review ([`docs/SECURITY.md`](docs/SECURITY.md)): rate limits, size limits, secure defaults, CORS; 4.4 Docker image, Compose stack and GitHub Actions CI
- [x] Tier 5: coordinator dashboard (React) and carer app (Flutter): review queue, overview and audit log, schedule map and trade-off, workforce risk with SHAP, carer visits and notes, live demo (see below)
- [x] Tier 6: packaging: final README, data-protection note, model cards

## Quick start

Prerequisites: Python 3.12 (managed by `uv`), Docker, Ollama; Node 24 for the dashboard; Flutter 3.35 for the carer app.

```bash
uv sync                                   # create .venv and install deps
uv run pre-commit install                 # git hooks: ruff + hygiene checks
cp .env.example .env
docker compose up -d db                   # PostgreSQL 16 on 127.0.0.1:5442
uv run alembic upgrade head               # create tables + append-only audit trigger
ollama pull llama3.1:8b                   # default LLM (qwen2.5:3b optional)
uv run pytest                             # tests
uv run python -m scripts.create_user coord.demo coordinator   # prompts for a password
uv run uvicorn app.main:app --reload      # API at http://localhost:8000/docs

# Every endpoint except /health and /auth/* needs a bearer token (Step 4.1):
TOKEN=$(curl -s -X POST localhost:8000/auth/token -d 'username=coord.demo&password=<yours>' \
  | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"       # used by the curl examples below

# Coordinator dashboard (Tier 5): http://localhost:5173, demo accounts on the sign-in page
uv run python -m scripts.seed_demo        # local/demo environments only
(cd web && npm ci && npm run dev)
# Carer app (Tier 5): Flutter web on http://localhost:8081, signed in as joy@demo.smartpbl
(cd mobile && flutter pub get && flutter run -d chrome --web-port 8081)

# Or run the whole stack in containers (Step 4.4): db -> migrate -> api on 127.0.0.1:8000.
# Ollama stays on the host (Metal GPU); the API reaches it at host.docker.internal.
docker compose up -d --build
docker compose exec api python -m scripts.create_user coord.demo coordinator

# Optional, Tier 2: road travel times (the committed matrix works without it)
scripts/prepare_osrm.sh                   # download West Midlands OSM + preprocess (~1 min)
docker compose --profile osrm up -d osrm  # OSRM on 127.0.0.1:5005
```

## Tier 1: care-notes NLP

A coordinator gets a queue of risk flags from carers' free-text visit notes. Each flag carries a verbatim quote, and every automated and human decision is in an append-only audit log.

### Architecture

```mermaid
flowchart LR
    N[POST /notes<br/>raw note] --> R[PII redaction<br/>Presidio + UK recognisers]
    R -->|redacted text only| L[Local LLM<br/>Ollama llama3.1:8b<br/>JSON-schema output, temp 0]
    R --> B[Rules baseline<br/>regex + negation]
    L --> V{valid?}
    V -->|no, retry once| L
    V -->|yes| G[Evidence grounding<br/>exact / normalised / fuzzy ≥ 90]
    B -->|categories the LLM missed| G
    G --> RT[Routing policy<br/>high severity, safeguarding,<br/>fuzzy/ungrounded, low confidence,<br/>rules-only, LLM failure]
    RT -->|auto-accept| DB[(Postgres<br/>notes, flags, decisions)]
    RT -->|needs review| Q[GET /review/queue]
    Q --> H[Coordinator<br/>POST /review/id<br/>approve / edit / reject]
    H --> DB
    R & L & B & RT & H -.->|HMAC input hash, model digest,<br/>prompt version, output| A[(audit_events<br/>append-only trigger)]
```

**Design principles:**
- **Data minimisation:** the LLM, the audit log and API responses never contain raw identifiers.
- **Local inference:** no note leaves the machine.
- **Every flag must quote the note,** and quotes that can't be found are rejected.
- **Nothing is silently dropped:** every flag is auto-accepted or queued, with reasons.
- **Graceful degradation:** if the LLM is down, the note is kept with the rules' flags and queued.

The design decisions behind each module are in [`DECISIONS.md`](docs/DECISIONS.md).

### Results: held-out test split

The test split has 40 synthetic notes, 56 gold flags and 8 per category, with seed 42. It was opened once, after all tuning was finished. Full tables, dev results and method: [`docs/results/tier1_eval_test.md`](docs/results/tier1_eval_test.md).

| System | Precision | Recall (95% CI) | F1 (95% CI) | Severity agreement | Median latency |
|---|---|---|---|---|---|
| llama3.1:8b + prompt v2 | 0.960 | **0.857** (0.776–0.930) | **0.906** (0.847–0.955) | 0.81 | 5.8 s |
| qwen2.5:3b + prompt v2 | 0.933 | 0.500 (0.391–0.618) | 0.651 (0.541–0.759) | 0.57 | 2.3 s |
| Rules baseline | 0.977 | 0.768 (0.642–0.885) | 0.860 (0.777–0.933) | 0.98* | 0.3 ms |

The deployed pipeline is llama + rules safety net + routing:

| Notes sent to review | Gold flags with no flag at all | High-severity escapes | Auto-accepted false positives | Schema-valid first try | Evidence grounded |
|---|---|---|---|---|---|
| 50% | 4 / 56 (7.1%) | 0 / 19 | 0 / 27 | 40 / 40 | 100% |

![Recall per category](docs/figures/tier1_recall_test.png)

![Category confusion](docs/figures/tier1_confusion_test.png)

**Reading the results honestly:**
- **The LLM vs the rules is not statistically settled at n = 40.** The paired bootstrap F1 difference is +0.046 (95% CI −0.034 to +0.141).
- **The rules overfit their tuning data.** They dropped from 0.986 F1 on dev to 0.860 on test, with 0.59 recall on test-only phrasings against the LLM's 0.81.
- **The two systems are complementary:** union recall is 0.929, which is why the rules act as a safety net.
- **\*The rules' severity agreement is inflated.** The same author wrote both the rules and the gold severities.
- **qwen2.5:3b finds about half the risks on both splits.** It is not a viable fallback without its own prompt work.
- **All four escaped flags use phrasings that appear only in the test split.** Examples: concealed medication ("pills hidden in a tissue"), a subtle mood change, and a shortened visit.

### Run the pipeline and the evaluation

```bash
# One note through the API (Ollama running):
curl -X POST localhost:8000/notes -H "$AUTH" -H 'content-type: application/json' -d '{"note_id":"DEMO-1",
  "client_ref":"CL-0001","carer_ref":"CR-0001","visit_time":"2026-11-07T08:00:00Z",
  "text":"Visited Mrs Testperson. Found her on the floor in the hallway. Refused morning tablets."}'
curl -H "$AUTH" localhost:8000/review/queue

# Re-score the committed predictions (no Ollama needed):
uv run python -m scripts.eval --split test --final
# Regenerate predictions from scratch:
uv run python -m scripts.run_extraction --split test --model llama3.1:8b --prompt v2 --final
```

### Tier 1 limitations

- **Synthetic, template-generated notes.** One author wrote the data, rules, prompts and labels, so the evaluation is partly circular and absolute numbers are optimistic. Real notes are longer, messier and contain risks spread across sentences.
- **Small test set.** 40 notes gives wide confidence intervals. The test set is now spent: any further prompt or rule iteration needs a fresh held-out set.
- **LLM self-reported confidence is uninformative:** 86% of flags have confidence 1.0. Routing therefore relies on policy, grounding and the rules safety net, not on confidence.
- **Grounding checks that a quote exists, not that it supports the flag.** A negation misread ("no signs of falls" flagged as a fall) passes grounding.
- **The audit log is append-only against the application only.** A database owner or superuser can disable the trigger. Production needs separate DB roles and tamper evidence such as a hash chain or write-once storage.
- **Authentication arrived in Step 4.1** (JWT + roles; the reviewer is the authenticated user). The API returns redacted text only.
- **Ingestion is synchronous** (6–18 s per note), and raw text is not encrypted at rest. Both are in [`BACKLOG.md`](docs/BACKLOG.md).

## Tier 2: carer matching

A day's visits are assigned to carers, respecting skills, shifts and arrival windows, while trading travel against continuity of care. Every assignment comes with checkable reasons.

### Architecture

```mermaid
flowchart LR
    SC[Scenario<br/>carers · clients · visits<br/>skills, shifts, windows,<br/>preferred/recent carers] --> V{integrity<br/>check}
    V -->|malformed| E[422]
    V --> TM[Travel matrix<br/>cached OSRM, West Midlands, car<br/>→ live OSRM → calibrated haversine]
    TM --> P1[Phase 1: OR-Tools VRPTW<br/>min driving + drop penalties<br/>time-critical ×2]
    P1 -->|warm start| P2[Phase 2: + continuity weight w<br/>new = w, recent = w/2, preferred = 0]
    P2 --> CK[Independent checker<br/>skills · windows · shifts · travel]
    CK --> EX[Explanations<br/>reasons per assignment,<br/>cause per unassigned visit]
    EX --> DB[(schedule_runs<br/>schedule_assignments<br/>no locations stored)]
    EX -.-> AU[(audit_events<br/>schedule_solved: params, seed,<br/>objective, solver version)]
```

**Design principles:**
- **Hard constraints in the model, preferences as priced costs.** w = minutes of driving accepted to send a familiar carer.
- **Never "infeasible".** An overloaded day returns the best partial plan, plus the reason each visit is unassigned.
- **Continuity never costs a visit.** A penalty guard plus the two-phase warm start ensure this.
- **Every solution is re-verified,** and every number is framed against a proven CP-SAT bound.
- **Client locations stay in-house:** self-hosted routing, and runs store only a keyed hash of the input.

### Results

**Travel times** (58 points, 3,306 ordered pairs; [`tier2_travel.md`](docs/results/tier2_travel.md)):
- Road distance is **1.34×** the straight line.
- The fitted fallback is **115 s + road distance at 42.3 km/h** (free-flow), with a mean absolute error of 1.3 minutes against OSRM.
- A naive straight line at 30 km/h underestimates by 1.4 minutes per trip.

**Baseline day** (seed 42: 17 carers, 106 visits; [`tier2_baseline.md`](docs/results/tier2_baseline.md)):
- OR-Tools leaves **12 visits unassigned** (11 with 60 s of search). A CP-SAT relaxation proves at least **2** are unavoidable even with zero travel.
- The causes are a morning dementia/catheter skill-mix bottleneck and an evening bed-time peak.
- Staffing what-ifs: training one carer and adding one late carer cuts unassigned visits to 7.

![Baseline routes](docs/figures/tier2_baseline_routes.png)

**Travel vs continuity** (94 visits with coverage fixed; [`tier2_continuity.md`](docs/results/tier2_continuity.md)):
- Familiar carers rise from **29% to 56%** as w goes from 0 to 30 minutes, against a proven ceiling of 81%.
- The first 7 points cost only 7 minutes a day.
- The middle of the curve costs about **6.5 minutes of driving per extra familiar visit**, and about 19 minutes past the knee at w ≈ 15.

![Travel vs continuity](docs/figures/tier2_pareto.png)

**OR-Tools vs a nearest-available-carer greedy**, mean over 5 synthetic days ([`tier2_comparison.md`](docs/results/tier2_comparison.md)):

| | Greedy | OR-Tools, w=0 | OR-Tools, w=15, two-phase |
|---|---|---|---|
| Unassigned visits (of ~106) | 25.2 | 17.8 | **17.0** |
| Time-critical visits unassigned | **5.4** | **0** | **0** |
| Driving (min/day) | 663 | **596** | 687 |
| Familiar carer (% of served) | 22% | 29% | **56%** |
| Runtime | 7 ms | 10 s | 20 s |

![Comparison](docs/figures/tier2_comparison.png)

**Reading the results honestly:**
- **The optimiser wins on coverage, driving and safety on every day tested.** Greedy's myopia costs about 5 time-critical medication visits a day.
- **Continuity has a clear price curve.** Choosing a point on it is a decision for the registered manager, carers and families, not a technical one.
- **Utilisation is only about 50–55% for every method.** Demand peaks at 08:00 and 20:00, so workforce design (split shifts, staggered starts) matters as much as routing.

### Plan a day through the API

```bash
uv run uvicorn app.main:app --reload
curl -X POST localhost:8000/schedule/solve -H "$AUTH" \
  -H 'content-type: application/json' -d '{"time_limit_s": 10, "continuity_weight_min": 15}'
# -> routes per carer with reasons, unassigned visits with causes, metrics, run id
curl -H "$AUTH" localhost:8000/schedule/<run id>

# Reproduce the Tier 2 results (OSRM optional; committed matrices are used):
uv run python -m scripts.solve_baseline     # strategies, bound, what-ifs (~5 min)
uv run python -m scripts.sweep_continuity   # Pareto sweep (~6 min)
uv run python -m scripts.compare_solvers    # greedy vs OR-Tools over 5 days (~3 min)
```

### Tier 2 limitations

- **One synthetic city day per seed.** The generator's staffing is tight for its demand peaks (12–27 visits unassigned even by OR-Tools). It rejected 3 of 8 seeds for skill-mix gaps, so the valid days are a filtered sample.
- **Simplified workforce:** everyone drives; continuous shifts without breaks; no double-up (two-carer) calls; waiting time isn't costed, which leaves visible 1–2.5 h mid-shift gaps.
- **Free-flow travel times.** OSRM has no traffic, so peak-hour Birmingham is slower than modelled. There's no parking or door-to-door overhead.
- **Heuristic search with a wall-clock limit.** Results vary a few percent between identical runs (3 of 10 sweep points changed on a rerun), and nothing is proven optimal. The proven bounds show the remaining gap.
- **The fair real-world baseline is PBL's actual rota,** replayed with call-monitoring data, not the greedy heuristic.
- **Synchronous API** (up to 60 s per request) with no authentication yet (Tier 4).

## Tier 3: attrition prediction

Predicts which carers are likely to leave within 12 months, so a coordinator can offer support with **working conditions the provider controls**: rota notice, unpaid gaps, regular clients, induction. The model card prohibits any adverse use.

### Architecture

```mermaid
flowchart LR
    T2[Tier 2 solves<br/>5 days, OR-Tools w=15] --> CD[85 carer-days<br/>driving · unpaid gaps · split days<br/>familiar-client share]
    CD --> GEN[Synthetic workforce, 1,000 carers<br/>+ assumed tenure, contract,<br/>short-notice changes]
    GT[Documented ground truth<br/>steps · hinge · interaction<br/>5 null features · hidden factor] --> GEN
    GEN --> CV[Nested 5x5 CV<br/>LR vs HGB<br/>tuned on log loss]
    GEN -.-> OR[Oracle: true P given features<br/>ceiling + calibration target]
    OR -.-> CV
    CV --> HGB[HGB, depth 2]
    HGB --> SH[SHAP, path-dependent<br/>additivity tested]
    SH --> API[GET /workforce/risk<br/>GET /workforce/id/explanation<br/>use notice in every response]
    API -.-> AU[(audit_events<br/>every read: viewer,<br/>carers shown, model version)]
    HGB --> FA[Age audit<br/>age never an input]
```

**Design principles:**
- **Features come from the scheduler,** so rota decisions (such as the continuity weight) feed directly into retention risk.
- **A known mechanism, stated up front.** Synthetic labels are circular, so the generator's ground truth is documented, and every result is read as "does the pipeline recover it?". This data says nothing about real carers.
- **Probabilities are the product.** Models are tuned on log loss, checked for calibration, and class reweighting is rejected.
- **Supportive by contract.** Factors are framed as provider levers with support actions; the label and age are never served; every view is audited.

The model card is [`docs/model-cards/attrition-model.md`](docs/model-cards/attrition-model.md).

### Results

**Data** ([data card](data/workforce/DATA_CARD.md)):
- **1,000 carers, 29.8% leavers.** The **oracle ROC-AUC is 0.726**: the best any model can do with these features. It is 0.754 even without the hidden factor, because the outcome itself is a coin flip.
- **The 200-carer test split is unusually easy** (97th percentile of possible splits), so cross-validation is the main estimate.

**Models**, nested 5×5 repeated stratified CV on 800 training carers ([`tier3_models.md`](docs/results/tier3_models.md)):

| | ROC-AUC | PR-AUC (AP) | Brier ↓ | Top-10% precision |
|---|---|---|---|---|
| Base rate | 0.500 | 0.297 | 0.209 | 30% |
| Logistic regression | 0.655 | 0.483 | 0.196 | 57% |
| LR, balanced class weights | 0.653 | 0.476 | 0.232 | 59% |
| **Gradient boosting (HGB)** | **0.675** | **0.538** | **0.188** | **69%** |
| Oracle (ceiling) | 0.709 | 0.556 | 0.181 | 71% |

- **HGB beats LR** in 18/25 folds on ROC-AUC, 20/25 on AP and 22/25 on Brier. It captures 84% of the achievable gain over chance, and its top-of-list precision is close to the oracle's.
- **Balanced weights:** same ranking, but mean predicted risk 48% against a true 30%.
- **The test split can't separate the models** (LR 0.772, HGB 0.759, CIs ±0.07).

![ROC and PR curves](docs/figures/tier3_roc_pr.png)

**Explanations vs ground truth** ([`tier3_explain.md`](docs/results/tier3_explain.md)):
- The global ranking matches the truth with Spearman **0.81**. Per-carer SHAP tracks true contributions for tenure, contract and short-notice changes (r ≥ 0.90).
- **Split shifts are under-credited** (r 0.13): the correlated unpaid-gap feature carries their signal. SHAP explains the model, not the world.

![SHAP vs truth](docs/figures/tier3_shap_vs_truth.png)

**Age audit** (age is never a model input): flagging the top 20% selects **47% of 18–24s and 8% of over-55s** (ratio 0.17), carried by tenure, while predictions stay roughly calibrated within each band. Accurate and disparate at once, which is why the controls are on use.

### Explore the workforce API

```bash
uv run uvicorn app.main:app --reload
# Needs a manager token (coordinators get 403): create_user manager.demo manager
curl -H "$AUTH" 'localhost:8000/workforce/risk?limit=5'
curl -H "$AUTH" localhost:8000/workforce/WF-0461/explanation

# Reproduce the Tier 3 results (deterministic):
uv run python -m scripts.calibrate_workforce  # re-solve Tier 2 days (~2 min; output committed)
uv run python -m scripts.generate_workforce   # synthetic workforce + oracle
uv run python -m scripts.train_attrition      # nested CV, test, calibration (~2 min)
uv run python -m scripts.explain_attrition    # SHAP, truth check, age audit (~30 s)
```

### Tier 3 limitations

- **Circular by construction.** Every metric measures recovery of a mechanism I wrote. The effect sizes are invented; only their directions follow UK care workforce reporting.
- **Small, simple workforce.** 1,000 carers from 84 Tier 2 rounds; employment features are mostly independent draws; one snapshot with no censoring; leavers aren't split by reason.
- **SHAP mode.** Interventional SHAP fails additivity for HistGradientBoosting in shap 0.54.1, so explanations use the path-dependent mode, which follows feature correlations.
- **Fairness audit covers age only,** because that's all the synthetic data contains. Real deployment needs audits of every lawfully measurable characteristic, a DPIA and worker consultation.
- **Access is manager-only since Step 4.1,** but not yet scoped per patch, and carers can't yet see their own explanation. The model retrains on first request (~4 s).

## Tier 4: production layer

The three AI modules sit behind one API that a care provider could put in front of real data, with work still to do (see limitations).

| Area | What is in place |
|---|---|
| Authentication | OAuth2 password login, short-lived JWT access tokens (15 min), refresh tokens rotated on every use with reuse detection (a replayed token revokes the whole session family), Argon2id password hashes |
| Authorisation | Routes depend on permissions, not roles; coordinator, manager and carer roles; least privilege (managers oversee but don't decide flags or run the solver); carers reach only their own data through `/me` |
| Audit | Middleware records every routed request (actor, route, outcome, subject) with a request id, correlated with the AI events; reads fail closed if the audit write fails; the audit table is append-only at the database level |
| OWASP API Top 10 | Rate limits (login, notes, solves), body and field size limits, secure start-up defaults (refuses dev secrets outside `local`), strict CORS, security headers, generic 500s, dependency vulnerability scan ([`SECURITY.md`](docs/SECURITY.md)) |
| Delivery | Two-stage, non-root Docker image; Compose stack (db → migrate → api, optional OSRM); GitHub Actions running lint, tests, a dependency audit, web and mobile builds and the Docker build, with actions pinned to commit SHAs |

## Tier 5: coordinator dashboard and carer app

```mermaid
flowchart LR
  subgraph Vercel
    D[React dashboard<br/>Vite · TanStack Query · typed client]
    C[Flutter carer app<br/>Riverpod · GoRouter · Dio · Wasm PWA]
  end
  D -->|JWT, coordinator / manager| A[FastAPI on Cloud Run]
  C -->|JWT, carer: /me routes only| A
  A --> N[(Postgres on Neon)]
  L[Laptop: Ollama] -.->|note extraction, local only| A
```

| Screen | Design | What it shows |
|---|---|---|
| Overview | `Main.dc.html` | What needs attention, flags by category, AI pipeline health, today's rota vs the greedy baseline, workforce check-ins |
| Review | `Review.dc.html` | Queue by severity (urgent concerns first), note with highlighted evidence, approve/edit/reject per flag, escalation |
| Schedule | `Schedule.dc.html` | Route map (OSM), timeline, "why this carer" with the next best option, travel vs continuity presets on the Pareto curve |
| Workforce | `Workforce.dc.html` | Carers by relative risk band, SHAP contributions in percentage points, supportive actions only |
| Audit log | `Audit.dc.html` | Every AI output, human decision, solver run and denied access, searchable, with CSV export |
| Carer app | `Visits`, `VisitDetail`, `Note`, `Submitted` | Today's visits from the saved rota, a handover of recent notes, a care note with tasks and an urgent concern |

**Engineering points:**
- **Typed client:** the dashboard's API client is generated from the OpenAPI schema, and a CI test fails if the client and the API drift apart.
- **Server-side access control:** pages hidden from a role still make their API request, so the server refuses it and the refusal is audited.
- **Carer data:** carers reach their data only through `/me` routes, with object-level ownership checks (OWASP API1).
- **Testing:** 87 dashboard tests (Vitest and Testing Library), 22 Flutter tests, and 436 API tests. Lint and type checks run in CI.

**Limitations of Tier 5:**
- **Single synthetic day:** "today" is the latest saved rota, and maps and locations exist only for the sample day.
- **No AI in the cloud:** the hosted demo has no LLM.
- **Sessions:** tokens live in memory, so a reload signs you out.
- **No offline mode:** the carer app needs a connection.
- **Not built:** parts of the designs with no backend yet (the carer Rota and My notes tabs, notifications, planning actions) are left out. They are listed in [`docs/BACKLOG.md`](docs/BACKLOG.md).
- **Visual review:** screens were compared against the designs by screenshot, not by a designer.

## Future work

The full list is in [`docs/BACKLOG.md`](docs/BACKLOG.md). With real PBL data, the priorities would be:

1. **Data protection first.** A DPIA, data-sharing agreement and Caldicott sign-off, then a fresh held-out evaluation on real, consented notes, with clinicians labelling severity.
2. **Notes pipeline.** Asynchronous ingestion (a job queue), encryption at rest for raw text, and a GPU inference server inside PBL's network (still no third-party LLM).
3. **Scheduling.** Dated multi-day rotas from PBL's rostering system, traffic-aware travel times, breaks and double-up calls. The baseline would be PBL's actual rotas, not a greedy heuristic.
4. **Workforce.** Retraining on real leaver records, fairness audits across every lawfully measurable characteristic, worker consultation, and patch-scoped access.
5. **Apps.** An offline-first carer app with a sync queue, push notifications, SSO, and per-patch scoping in the dashboard.

## Documentation

| Read this | For |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture Decision Records (ADR-001 onwards) |
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | Known gaps and future work |
| [`docs/SECURITY.md`](docs/SECURITY.md) | OWASP API Top 10 review and what was addressed |
| [`docs/DATA_PROTECTION.md`](docs/DATA_PROTECTION.md) | DPIA-style note: lawful basis, minimisation, retention, risks and mitigations |
| [`docs/model-cards/`](docs/model-cards/) | Model cards: [extraction pipeline](docs/model-cards/extraction-pipeline.md), [attrition model](docs/model-cards/attrition-model.md) |
| [`docs/results/`](docs/results/), [`docs/figures/`](docs/figures/) | Every reported metric, with test-set size and seed |
| [`data/*/DATA_CARD.md`](data/) | How each synthetic dataset was generated, and its biases |

## Layout

```
app/        core (config, db) · nlp (schemas, redact, baseline, extract, ground, route, review, evaluation)
            matching (data, travel, solver, check, bounds, continuity, greedy, explain, service)
            workforce (data, features, models, explain, service) · audit · api
prompts/    versioned prompt templates          data/      synthetic notes, data card, cached predictions
scripts/    data generation, extraction, eval   migrations/ Alembic
tests/      unit + Postgres integration tests   docs/      decisions, results, figures, model cards
web/        React coordinator dashboard         mobile/    Flutter carer app (web PWA + Android/iOS)
```

## Limitations

- **Synthetic data throughout.** One author wrote the generators, rules, prompts and labels, so every evaluation is partly circular and absolute numbers are optimistic. The data cards describe each dataset's biases ([notes](data/care_notes/DATA_CARD.md), [scheduling](data/scheduling/DATA_CARD.md), [workforce](data/workforce/DATA_CARD.md)).
- **Small evaluation sets.** 40 test notes, 5 scheduling days and 200 test carers give wide confidence intervals; the intervals are reported with every result.
- **Single machine and single synthetic day.** Developed and tested on one Apple M1 Pro (16 GB). "Today" is the latest saved rota, and the hosted demo has no LLM.
- **Prototype security.** Tokens live in memory, rate limits are in-process, the audit log is append-only against the application but not tamper-evident, and raw note text is not encrypted at rest.

Each tier section above lists its own limitations in detail.
