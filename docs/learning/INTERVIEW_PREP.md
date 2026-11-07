# Interview Prep: Cumulative Q&A bank

## Setup / Infrastructure

**Why run the LLM locally rather than call a hosted API?**
Care notes are special-category health data under UK GDPR (Article 9). A hosted API makes the provider a processor, which brings contracts, transfer checks and a broader DPIA. Local inference keeps data on infrastructure PBL controls. The trade-off is lower model quality and running the model ourselves. That is acceptable for narrow extraction that is human-reviewed and evaluated against a baseline.

**How did you choose the model size?**
I matched it to the hardware: 16 GB of unified memory fits an 8B model at Q4 (~4.9 GB). A 3B model is also pulled, so Step 1.9 measures the quality-versus-latency trade-off instead of asserting it.

**What is quantisation and what does it cost you?**
Fewer bits per weight (e.g. 4-bit with block scales) means about 4× less memory and faster, bandwidth-bound inference. The cost is a small accuracy loss, which may show up in negation handling. That's why negated cases are in the eval set.

**Why pin Python 3.12 when 3.14 was available?**
The spaCy and Presidio wheels lag new Python releases. Pinning prevents a broken install halfway through the build. The pin is enforced by `.python-version` and `requires-python`.

**With real PBL data and at scale, what changes?**
A dedicated inference server inside PBL's network (or vLLM on a GPU), with auth and TLS. Managed, encrypted Postgres. A secrets manager. Readiness probes. The architecture stays the same.

**Trade-off: why not containerise Ollama too?**
Docker on macOS has no Metal GPU, so the model would run CPU-only and distort the latency results. I chose correct performance over one-command setup. On a Linux GPU server I would containerise it.

## Tier 1 — Care-notes NLP

### 1.1 Schemas
**How does schema design affect LLM reliability?**
Closed enums remove free-text variation. `required` plus `additionalProperties: false` stop omitted or invented fields. Field order shapes conditioning (evidence before severity). Descriptions act as inline instructions. Keep schemas small and flat.

**Why a verbatim quote rather than character offsets?**
LLMs work in tokens and can't count characters reliably, but they copy text well. A quote can be verified as a substring (exact or fuzzy) to reject hallucinations. Offsets are computed afterwards, deterministically.

**If decoding is constrained, why validate with Pydantic too?**
Defence in depth: grammar engines may not enforce every keyword (length, numeric bounds), and output can be truncated. And a schema guarantees shape, not truth. My sanity check gave a valid extraction that missed a fall.

**Trade-off: does forcing JSON make the model worse?**
It can for reasoning-heavy tasks (Tam et al., 2024, "Let Me Speak Freely?"), while classification often benefits. Ours is closed-taxonomy extraction. Evidence-first ordering acts as built-in reasoning. If recall suffered, test a two-step reason-then-format approach in eval.

**Why three severity levels?**
Each maps to one action (record, same-day follow-up, same-shift escalation). More levels add disagreement without adding decisions. With real data: agree definitions with registered managers and measure inter-annotator agreement (Cohen's kappa).

**With real PBL data, what changes in the schema?**
Validate the taxonomy against PBL's incident categories and CQC reporting. Add `schema_version` to audit records. Possibly use client context for severity, under strict access control.

**Why is self-reported confidence not a probability?**
It's generated text, not calibrated, and tends to cluster high. Use it only to rank and route, and send high-severity flags to review regardless. Better signals: token log-probs or agreement across samples, calibrated against labels.

### 1.2 Synthetic data
**Why templates instead of LLM-written notes?**
Labels are correct by construction. LLM-written notes need labels, and LLM labels used to evaluate an LLM are circular. Templates are also deterministic and reviewable. The cost is narrow vocabulary, which is documented and partly offset with indirect, negated, held-out and noisy cases.

**What is data leakage and where could it happen here?**
Evaluation information influencing the system under test. Here: phrase leakage, where rules or prompts written on dev match identical test phrases. Fix: 14 test-only phrases plus an `unseen_phrase` tag to report seen vs unseen.

**Why not just change the seed when coverage was thin?**
Choosing a seed because it passes a check is mild p-hacking. Balanced assignment makes coverage structural, and it's tested across several seeds.

**What biases does the dataset have?**
Narrow vocabulary (favours keywords), artificial prevalence (83% risky, so precision is inflated), few low-severity cases, female clients only, simple negation, one risk per sentence. Present results as a comparison between methods, not accuracy on real data.

**With real PBL data, how would you build the evaluation set?**
DPIA and data-sharing agreement first. De-identify. Stratified sample. Two trained annotators with guidelines, Cohen's kappa measured. Split by client. Keep the synthetic set as a regression suite.

**Trade-off: controlled difficulty vs realism?**
Controlled data diagnoses *which* skill fails. Real data measures *how much* it matters. You need both, like unit tests vs integration tests.

**How is the dataset reproducible and tamper-evident?**
A seeded local RNG; a test that two runs are identical; committed JSONL compared with a fresh generation in CI.

### 1.3 PII redaction
**The LLM is local. Why redact at all?**
Data minimisation (Art. 5(1)(c)) applies regardless of where processing happens: identifying a fall doesn't need a name. Redaction also protects against logs, traces, a future hosted model, and identifiers copied into summaries. Defence in depth; central to the DPIA.

**Why recall over precision, and where does it stop?**
The costs are asymmetric (breach vs a lost word). So: no NHS checksum, low threshold, layered recognisers. It stops where clinical meaning breaks: case-insensitive kinship matching gives 100% recall but test evidence preservation falls to 83.9%. Track both metrics.

**How do you know it works?**
Per-recogniser unit tests, clinical sentences preserved, dataset floors (test recall 98.3%, evidence 96.4%). Tuned on dev only. Residual gap documented: lowercase word-like family names. Synthetic data overstates real recall.

**What changes with real PBL data?**
A gazetteer from the care record (the `known_names` hook), a double-annotated de-identification test set with recall per entity type, possibly trf or fine-tuned NER, carer names. All inside PBL under the DPIA.

**Typed placeholders vs consistent pseudonyms?**
Typed tags leak nothing but lose who did what, which matters for safeguarding. Numbered pseudonyms within a note keep relationships, at the cost of a sensitive mapping. Start simple; switch if evaluation shows lost relationships hurt.

**Can the LLM do the redaction?**
Not as the gate: that sends raw PII into the model, and it's non-deterministic and hard to audit. At most a second-pass detector on already-redacted text.

**Is redacted text anonymous?**
No. It's pseudonymised at best (linked to client_ref, original stored, context can re-identify), so it's still personal data.

### 1.4 Rules baseline
**Why a rules baseline when you have an LLM?**
LLM metrics are meaningless without a comparison. If rules match, they win on cost, determinism, auditability and zero hallucination. The baseline also shows where the LLM should add value (typos, indirect phrasing). Rules of ML #1.

**Dev F1 went from 0.79 to 0.99. Is it that good?**
No: tuning-set optimism. Honest numbers come from test, especially the unseen-phrase subset, in 1.9. No drop there would suggest test phrases are too close to dev.

**How does negation work and where does it fail?**
Simplified NegEx: a cue ≤5 tokens before the trigger, scope ends at "but", negation-containing patterns exempt. Fails on post-negation ("falls: none"), long scope, double negation, hedging. A real bug: "NHS no" read as negation, fixed as a general case.

**Why not fuzzy matching for typos?**
False positives on short words (fall/tall/fail), threshold tuning, and it blurs what the baseline is. Typo robustness is something to measure in the LLM.

**Keep rules with real PBL data?**
Yes, as a high-precision safety net for unambiguous high-severity triggers, independent of the LLM, and to flag LLM omissions. spaCy matchers, versioned rules. TF-IDF + LR once labels exist.

**Why macro as well as micro F1?**
Micro hides failure on rare categories (safeguarding). Macro weights each category equally. Also look at per-category recall.

**You wrote the test phrases and the rules. Compromised?**
Partly; acknowledged. Mitigated with a generic v0, logged dev-only changes, and a closed test set. The real fix is separation of roles or real notes labelled by care staff.

### 1.5 LLM extraction
**How do you get reliable structured output from a local LLM?**
Schema-constrained decoding (Pydantic schema → Ollama `format`), Pydantic validation, one retry with the error fed back, then human review. 160/160 valid on dev, but validity ≠ correctness, so recall, grounding and severity are measured separately.

**Why temperature 0, and what doesn't it guarantee?**
Greedy decoding gives reproducible evaluation and replayable audits. It doesn't guarantee correctness (consistently wrong), nor identical output across engine versions, quantisations or hardware. So I record the model digest.

**Why version prompts in files with a hash?**
Prompts are code. The label is for people; the hash catches silent edits. Every output stores prompt version and hash plus model and digest. Prompt changes go through dev evaluation (v1 → v2).

**Your outputs contradicted themselves 9/80 times. What did you do?**
Derive `follow_up_required` from severities in code and log overrides: dev accuracy 0.825 → 0.938. The LLM does language understanding; code does deterministic functions.

**Can you use model confidence for routing?**
No. 97% of flags at 0.8–1.0 in v1; asking for lower values made it worse (86% at 1.0). Route on severity, grounding and agreement with the baseline. Better: log-probs or agreement across samples, calibrated.

**Trade-off: why stop at prompt v2?**
More iterations mean more dev overfitting. The remaining errors would need near-copies of dev phrases. Check in 1.9 whether the rules cover them (time comparison), which points to a hybrid. With real data, use a separate prompt-development set.

**With real PBL data and at scale?**
5–9 s/note is fine asynchronously. At scale: a queue with workers and a GPU inference server inside PBL's network; evaluate qwen2.5:3b against recall targets; monitor validity and retry rates; re-evaluate whenever the model digest changes.

### 1.6 Grounding and routing
**How do you control hallucination?**
Layers: constrained shape; every flag quotes evidence that is checked against the redacted note (exact → normalised → fuzzy ≥ 90, ≥ 3 words); ungrounded flags are never auto-accepted. Dev: 0 ungrounded, but adversarial tests prove rejection. Wrong conclusions from real text are left to routing and evaluation.

**How did you choose the threshold?**
Data: genuine ≥ 98.1, negatives p99.9 = 66.7. Maths: one swap costs 1/L, so 90 tolerates one typo fix at ≥ 10 chars. Costs: a false accept passes a hallucination; a false reject costs seconds. "heels look sore" vs "red" scores 86.7, so 85 would have been unsafe.

**What is HITL here, and why does it matter legally?**
High and safeguarding flags always go to a coordinator, plus fuzzy, ungrounded, low-confidence and baseline-only ones. The system never closes a risk alone. Art. 22A (DUAA 2025): solely automated = no meaningful human involvement; review should come after the output and concern the outcome, so no rubber-stamping, and workload must stay manageable.

**Workload vs safety trade-off?**
Dev: 59% reviewed / 10.1% escaped (LLM only) vs 64% / 0% (with the rules safety net, optimistic). Synthetic prevalence inflates workload. With PBL: present a review-vs-escape curve and let the registered manager choose the operating point.

**What doesn't grounding protect against?**
Real quotes supporting wrong conclusions (negation: "falls" in "No falls"; wrong category), and omissions. Next step: entailment checks for high-impact categories; recall measured in eval.

**With real PBL data?**
Recalibrate the threshold; set routing with the registered manager and safeguarding lead; measure reviewer time and agreement; monitor fuzzy/ungrounded rates as drift alarms; calibrated uncertainty instead of confidence.

**Why keep a confidence rule that never fires?**
Spec requirement, no cost, works automatically if confidence improves. But I report that it fired 0 times, so nobody counts it as an active safeguard.

### 1.7 Persistence and audit
**Why append-only, and how is it enforced?**
An audit log is only evidence if it can't be changed. A DB trigger rejects UPDATE/DELETE/TRUNCATE for every client; a mutation test proves the tests depend on it. Limitation: the owner or a superuser can disable/drop it. Production: app role with INSERT/SELECT only, separate migration role, hash chain or external immutable store.

**Why store a hash, not the input?**
Prove which input produced an output without making the log a second, longer-lived copy of health data. The log can outlive the note (storage limitation/erasure), hence no foreign key.

**Why HMAC, not plain SHA-256?**
Short, formulaic notes allow dictionary attacks on plain hashes. HMAC needs the key to test a guess, stays deterministic, `hash_alg` is stored for rotation, and the key belongs in a secrets manager.

**LLM latency vs transactions?**
Model work first, then one short transaction. Never hold a transaction across a slow external call (pool exhaustion, locks). A crash between the two just redoes deterministic work.

**What if Ollama is down?**
Catch, record `extraction_failed`, keep baseline flags, queue for review. Tested. Production: queue retries with backoff, alert on failure rate.

**Mutable review_status alongside an audit log?**
Current state for fast queue queries; full history in the append-only log, written in the same transaction. A pragmatic split vs full event sourcing.

**With real PBL data?**
Encryption at rest for raw_text, a retention job, separate DB roles, the HMAC key in a secrets manager with rotation, export to immutable storage, audit of reads too (Tier 4).

### 1.8 API and human review

**Two coordinators review the same flag at once?**
`SELECT … FOR UPDATE` serialises them. The second waits, sees "approved", and gets 409. Without the lock you get a lost update. A test asserts the lock is emitted.

**Why can't reviewers type any evidence?**
It is re-grounded against the redacted note, and the note's own span is stored. The "evidence is in the note" invariant holds for human edits too, and names can't be typed in.

**Comments vs the audit log?**
Comments contain names, and the audit log is permanent. So the comment lives in `review_decisions`, which retention applies to, and the log records only `has_comment`.

**Synchronous `POST /notes` at 6–18 s?**
It's simplest for a prototype, and the pipeline degrades to the baseline if the LLM fails. At scale: 202, a queue, workers with retry, and idempotency keys. `process_note` is already independent of HTTP.

**Why separate API schemas from ORM models?**
The API is a privacy boundary. A new column must not leak automatically (OWASP API3, excessive data exposure). A test fails if `raw_text` or PII appears in a response.

**Is `X-Reviewer` auth?**
No. It is a declared stand-in so the audit actor field is populated. It is replaced by the JWT subject and a role check in 4.1, and it is already a dependency.

**Why can auto-accepted flags be overridden but human decisions can't?**
Policy decided the first, so a human override is the system working. Human decisions carry accountability, so re-opening one must be an explicit, audited action.

**With real PBL data?**
- Authenticated roles, and auditing of reads.
- Raw text for authorised roles only.
- Async ingest with idempotency keys.
- ETags for long-lived review screens.
- A priority column with SQL paging.
- Reviewer decisions as the labelled dataset, with edit rate monitored as a drift signal.

### 1.9 Evaluation

**Which metric matters most for safety flags?**
Recall, because a miss can mean harm and a false positive costs a minute. Precision still matters (alert fatigue), so report F1 too. The deployed headline is the escape rate: 7.1%, with 0/19 high-severity escapes, at 50% review workload. As a single number, F2.

**Is the LLM better than the rules (0.906 vs 0.860 F1)?**
Not provably at n = 40. Paired bootstrap: +0.046 (−0.034 to +0.141), p ≈ 0.14. What is robust: the rules drop 20 points of recall on held-out phrasing, and union recall is 0.929.

**Why did the rules drop from 0.986 to 0.860?**
Hand-tuning on dev phrasings is overfitting. On test-only phrasings recall was 0.59 for the rules vs 0.81 for the LLM. That is why the test split stayed locked until the end.

**llama 8B vs qwen 3B?**
qwen is 2.5× faster and smaller but finds half the risks, consistently on both splits. Triage is async, so latency is irrelevant and misses are not.

**How do you know the evaluation code is right?**
- It reproduces earlier, independently measured dev numbers.
- 13 unit tests with known answers.
- One wrong test expectation was caught: a paired p-value can't be exactly 0.
- Predictions are committed, so the results can be re-run.

**With real PBL data?**
- Double-annotated notes with kappa.
- A time-based split.
- Hundreds of examples per rare category.
- Fairness slices.
- Reviewer edit and reject rates as a live quality signal.

**What doesn't the synthetic evaluation tell you?**
Absolute performance (it's circular: one author for data, rules and prompts), messiness of real notes, and how humans use the queue. It does support relative comparisons, failure modes, and a ready harness.

## Tier 2 — Carer matching

### 2.1 Scheduling data

**Hard vs soft constraints?**
Hard constraints are those where violation is unsafe or unlawful: skills, shift, arrival window (especially time-critical medication), duration. Soft constraints are preferences such as continuity and travel. Hard ones go in as constraints, soft ones as explicit weighted costs.

**Why arrival windows?**
Care plans and call monitoring use them. In OR-Tools, the time dimension's value at a node is the arrival time, and duration is service time.

**How did you make the data solvable but not trivial?**
A validator checks that every visit's full skill combination exists on a covering shift, and the generator won't write a failing scenario. Per-skill coverage alone was shown to be insufficient. Capacity is left tight: the morning peak is about 90% loaded.

**Why no split shifts or double-ups?**
Both are real, and both need extra solver machinery (breaks, cross-vehicle synchronisation). They're documented as the first additions for PBL.

**With real PBL data?**
Postcode-centroid locations under a DPIA, travel modes (walking, bus), preferences from visit history, contractual rules, and many historical days.

**Why round synthetic coordinates?**
A random full-precision point can sit on a real front door. At ~100 m, travel times barely change. Production needs approximate locations, not addresses.

### 2.2 Travel times

**Why road time ≠ straight line?**
- Detour: about 1.34×.
- Fixed overhead per trip: about 2 min.
- Road-class speeds.
- Asymmetry: up to 3.2 min.

A naive straight line at 30 km/h is biased by −1.4 min/trip, about 2.5 h per day: schedules look feasible when they aren't.

**Why self-host OSRM?**
Free, private (client locations stay in-house) and reproducible (pinned map). The cost is free-flow speeds; a commercial traffic API would need a DPA and DPIA.

**Why calibrate a fallback?**
Tests and CI shouldn't need the routing graph, and an uncalibrated fallback misleads. The fitted model gives a known error budget: bias 0, MAE 1.3 min, max 6.8 min.

**How do you avoid stale caches?**
The key is the ordered points plus the backend, including the map MD5. Each matrix records its backend.

**At scale or with real data?**
Time-of-day travel times, travel mode per carer, parking overhead from call monitoring, per-patch caching, postcode-centroid precision.

**MLD vs CH?**
CH is the fastest to query but slow to reweight. MLD's cell partition allows re-customisation in seconds, keeping traffic updates possible.

### 2.3 VRPTW baseline

**Model?**
Carer = vehicle (start at home or office, open end). Visit = node. Time dimension in seconds (drive + service), with windows and shifts as limits on it. Skills restrict each visit's vehicle domain. Objective: drive time + drop penalties.

**Day over capacity?**
Visits are optional. Penalty 1M > maximum possible driving (446k s), so visits are dropped only when forced; time-critical ×2. A CP-SAT travel-free relaxation proves ≥ 2 drops are unavoidable; the best found is 11.

**Why did PATH_CHEAPEST_ARC look cheapest but do worst?**
374 min of driving because it dropped 47 visits. Myopic route-by-route construction gives up easily with optional nodes. Parallel insertion dropped 15. Compare on the full objective.

**First solution vs metaheuristic?**
Construction builds a solution fast. Local moves improve it until a local minimum. GLS, tabu or annealing then escape. Greedy descent stalled at 13 drops; tabu reached 11.

**How do you know solutions are valid?**
An independent checker re-derives arrivals from the matrix and checks every constraint. Every row reports it, a doctored-solution test exercises it, and a mutation check confirms it.

**With real PBL data at scale?**
Partition by patch, double-ups, split shifts and breaks, costed waiting and overtime, time-dependent travel, locked assignments with re-optimisation, many historical days.

**Waiting not costed?**
It shows up as 1–2.5 h unpaid gaps (an attrition risk). Span or waiting costs are the next lever, to be measured, not silently added.

### 2.4 Continuity of care

**How is continuity modelled?**
As a soft per-visit penalty (new w, recent w/2, preferred 0), implemented as a per-carer arc cost on arrival. w is in minutes of driving, which is interpretable. A guard means a stranger always beats no visit.

**Pareto front?**
The non-dominated schedules. The weight sweep traced 29% familiar at 597 min to 56% at 753 min, with a proven ceiling of 81%.

**What went wrong in the first sweep?**
Drop counts varied (12–14) from heuristic noise, so higher-weight points looked cheaper. Fixed lexicographically: freeze coverage, warm-start from the reference routes. Control the objectives you're not studying.

**How does a provider choose a point?**
- Price it: about 6.5 min (≈ £2.50) per extra familiar visit mid-curve.
- Take the near-free first 7 points.
- Set policy floors by client group.
- Find the knee.
- The manager decides; the tool shows the prices.

**Why not 100%?**
A CP-SAT travel-free ceiling of 81%: familiar skilled carers are wanted by many clients at the same peak times. Closing that gap takes workforce levers.

**With real data?**
Familiarity from visit history (recency-weighted), week-level planning, weights by need, validation across days, and measuring client-reported outcomes.

**Higher weights got worse?**
A rugged landscape for local search, so it's a search artefact. The front is computed from all points; cap w at about 30 min or give it more time.

### 2.5 Greedy baseline and evaluation

**Optimiser vs simple heuristic?**
Over 5 days: unassigned 17.8 vs 25.2, 10% less driving, 0 vs about 5 time-critical drops a day. w=15 two-phase gives 56% familiar for +15% driving with no coverage loss. All solutions checked.

**Why does greedy fail time-critical visits?**
Time-ordered and never revisits choices, so qualified carers get used up on routine visits. OR-Tools prices critical drops ×2 and rearranges routes. Fixing greedy needs look-ahead, which means writing an optimiser.

**When would you use greedy?**
Live same-day re-assignment (milliseconds), as a fallback, and for transparency. OR-Tools for the overnight plan.

**Why five days?**
Choices were tuned on seed 42; evaluating there is like testing on training data. The ranking held on all days. Rejected seeds are reported.

**Why is utilisation about 50–55%?**
Peaks bind, not total hours. Continuous shifts mean waiting through troughs. Levers: split shifts, staggered starts, moving flexible calls.

**With real data?**
Replay historical days against the actual rota using call-monitoring data, a shadow-mode pilot (measure acceptance and overrides), client outcomes (missed medication, complaints, continuity) and carer outcomes (idle time, mileage).

### 2.6 Schedule API and explainability

**Why was a carer assigned?**
Recomputed facts: skills, drive time and from where, arrival vs window, familiarity, other eligible carers. Drops are classed no-eligible (structural: train or hire) or eligible-busy (capacity: change the rota).

**What do you store?**
Run parameters, results, reasons and audit. Not the scenario (it has client locations): HMAC of canonical JSON, name and seed only.

**Partial plan vs rejection?**
An impossible visit is a workforce fact, not a malformed request: plan the other 105 and flag it. Malformed input still returns 422.

**Hash bug?**
Frozenset order wasn't stable, so equal inputs gave different hashes. Fixed with canonical (sorted) serialisation, and tested end to end.

**At scale?**
Async jobs (202 plus status), auth and roles, counterfactual "why not X?", a generic audit subject id, locked assignments with re-solve, retention.

**Arrival timing change?**
Latest-departure finalisers put visits at the end of their windows, which is brittle. Now earliest service and latest departure; same routes and objective, slack where it protects clients.

## Tier 3 — Attrition prediction

### 3.1 Synthetic workforce data

**What can a model on synthetic data tell you?**
Only that the pipeline works: it recovers planted effects, ranks null features near zero, and is calibrated against a known truth. Nothing about why real carers leave; every effect was put there by me.

**What is the oracle?**
P(leave | observed features), averaging over the unobserved factor. It gives a ceiling (AUC 0.726), a calibration target, and a leakage alarm (beating it on held-out data means leakage).

**Why derive features from Tier 2?**
It makes it one platform: driving, unpaid gaps, split days and continuity come from real routes, so scheduling choices feed retention risk. Real data would also come from rota and call-monitoring systems.

**Age band in the data?**
For auditing only, excluded from features by a test. 18–24s leave at 47% vs 23% for 55+ through tenure and contract alone, which is proxy discrimination in waiting. The use decides acceptability: mentoring yes, hiring or shift allocation no.

**Why keep an easy test split?**
The split rule was fixed in advance. Re-drawing it would be selecting the test set by its results. The oracle's test AUC spans 0.65–0.80 across splits with 60 leavers, so CV is the main estimate and test scores are quoted next to the oracle.

**Classification vs survival analysis?**
Classification is simpler to explain and calibrate, but loses timing and ignores censoring. With real data: a fixed label window with full follow-up, then survival models (Cox, boosted survival).

**With real PBL data?**
Snapshot features with no post-snapshot leakage, a time-based split, leaver reasons separated, a DPIA and worker consultation (this is employee profiling), and modest AUC expectations.

**Why null features?**
To catch explanation errors. The correlated pair (gaps and split shifts, r = 0.82) tests shared or swapped attribution.

### 3.2 Models: LR vs HGB, calibration

**Which model and why?**
HGB: better than LR in 18/25 CV folds on AUC, 20/25 on AP and 22/25 on Brier; 84% of the achievable gain over chance vs 74%; top-10% list 69% true leavers vs 57% (oracle 71%). LR stays as a challenger.

**Test says LR is better?**
0.772 vs 0.759 with ±0.07 intervals: indistinguishable with 60 leavers. CV was pre-committed as the main estimate because the split was known to be easy.

**Class weights or SMOTE?**
Same ranking (AUC 0.653 vs 0.655), but mean risk 48% vs a true 30%, and Brier worse in 25/25 folds. Lower the threshold on a calibrated model instead.

**Why PR-AUC?**
It matches the retention budget question (of those flagged, how many leave?), and its chance level is the base rate. ROC-AUC is blind to prevalence.

**How was calibration checked?**
Reliability diagram (OOF, 10 quantile bins), Brier vs the 0.21 base-rate bar, and error vs the true probability (synthetic only). No post-hoc calibration: already calibrated, and isotonic would overfit 800 rows.

**Black box in HR?**
Shallow, cautious HGB plus per-prediction SHAP (3.3). If coefficient-level transparency were mandated: LR with domain-agreed engineered features.

**With real data?**
A time-based split, wide CIs with a few hundred carers, drift monitoring and recalibration, voluntary-leaver labels, and a fairness audit first.

**What does nested CV protect against?**
Optimism from tuning on the scored folds (my exploratory peek). The inner grid search runs on the 640 training rows only; a test logs every fit and predict to prove the 160 validation rows stay unseen.

### 3.3 Explainability and model card

**How do you explain one carer's risk?**
SHAP top-5 in plain units, with direction, whether the provider can change it, and a support action. The values add up exactly to the score (tested). Lead with levers: the action is a better rota.

**How do you know the explanations are right?**
Synthetic: true Shapley values of the generator vs model SHAP give Spearman 0.81, and r > 0.9 for tenure, contract and changes. It also found that split shifts are under-credited because gaps carry their signal. Real data: stability across retrains, agreement with LR, coordinator review.

**Age removed: fair now?**
No. Top 20% = 47% of 18–24s vs 8% of 55+ (ratio 0.17), via tenure, while calibrated within groups. Accurate and disparate. The control is on use (support only) plus a published audit.

**Why not interventional SHAP?**
It failed additivity for HGB in shap 0.54.1 (exact for GradientBoosting), so path-dependent mode, the check left on, and a regression test. Never disable `check_additivity`.

**SHAP vs LR coefficients?**
LR: exact and global, but misses the step and interaction (−12 points top-10% precision). SHAP: faithful local attributions of the better model, but not causes, and credit swaps between correlated features.

**Ethical risks?**
Punitive use and self-fulfilling flags; proxy age discrimination; surveillance. Mitigations: prohibited uses, lever framing, audited role access, an outcome review of support offered, worker consultation, the right to contest.

**With real data?**
DPIA and consultation first, audits of all lawfully measurable characteristics, explanation stability checks, and recording interventions to avoid feedback-loop bias.

**A null feature appears in an explanation?**
The model fitted noise (a split at 25.55 h); SHAP faithfully reports the model's error. Present explanations as factors to discuss; don't act on small contributions.

### 3.4 Workforce API

**Walk me through it.**
`/workforce/risk` (ranked, top 3 factors, support priority for the top 20%) and `/workforce/{ref}/explanation` (12 additive SHAP factors, baseline vs average risk, support actions, caveats). A use notice in every response; every read audited; out-of-sample scores only.

**Why retrain at start-up?**
Pickle runs arbitrary code on load and isn't supported across sklearn versions. A 4 s deterministic retrain plus a version digest; in production, a registry with skops artefacts.

**Why audit reads?**
Misuse of employee risk happens by reading. Log viewer, carers shown and model version, committed with the request.

**What's left out of responses?**
The label (future outcome) and age band (protected). Explicit response models (OWASP API3:2023), with a test scanning the raw JSON.

**In-process vs separate scoring service?**
In-process: simple, fine for 150 trees. Separate: independent scaling and canaries, but more infrastructure; a score table stores derived personal data.

**With real data?**
JWT roles and per-patch scoping, carer self-access and contest, a snapshot date in the response, drift monitoring, a DPIA and audit retention.

**average_risk vs baseline_risk?**
Mean probability 0.306 vs sigmoid(mean log-odds) 0.282; Jensen's inequality. Named apart and tested.

## Tier 4 — Production layer

### 4.1 Auth and RBAC

**How is a request authorised?**
Bearer access token → decode (HS256 pinned; exp, iss, aud, required claims, type = access) → load the user by `sub` (must be active) → `require(permission)` against the current role. 401 if unknown, 403 if not allowed. Runs at router level, before validation and expensive dependencies. The authenticated username goes into the audit and review tables.

**JWTs are stateless: why the DB hit?**
Real revocation: disabling or demoting takes effect on the next request. One PK lookup per request; forged and expired tokens are still rejected by the signature alone.

**Refresh rotation and reuse detection?**
Single-use refresh tokens in a family per login; the old token is revoked and linked to its replacement. Reuse means two holders, so revoke the family (RFC 9700 §4.14.2). The revocation is committed before the 401; the row lock stops a double refresh.

**Why not opaque sessions?**
Equally defensible here. JWT was specified, gives clients a signed role for UI routing, and allows verification without a session store if the system splits.

**Who can do what, and how do you keep it right?**
Carers create notes; coordinators act (review, solve); managers oversee (audit, workforce risk). Least privilege plus separation of duties. One permission table, pinned by an independent route × role matrix test plus a deny-by-default guard test; mutation-tested.

**Enumeration and brute force?**
Identical 401s, and a dummy Argon2 verify for unknown users. Argon2id at 64 MiB/t = 3/p = 4 and a 12-character minimum. Login rate limiting comes in 4.3 (OWASP API2).

**With real PBL staff?**
Entra ID via OIDC (SSO, MFA, leavers handled by HR processes); RS256 verified against the IdP's keys; IdP groups mapped to the same roles and tests. Per-patch scoping, carer self-access, auth events audited.

**Where do browser clients keep tokens?**
Access token in memory; refresh token in an httpOnly, Secure, SameSite=Strict cookie scoped to `/auth/refresh`, plus CSRF protection. Mobile: platform secure storage. Decided with CORS in 4.3.

### 4.2 Unified audit

**How is auditing unified?**
An ASGI middleware writes one access row per routed call (actor, route template, status, typed subject); domain code writes decision events in-transaction; a request id (also `X-Request-ID`) joins them.

**Fail closed?**
Reads: buffer, commit the audit row, then send; on failure a 500 and no data. Writes: already committed with their domain events, so return the true outcome and log the failure (a 500 would invite a duplicate retry).

**Why pure ASGI?**
`BaseHTTPMiddleware` breaks upward context-variable propagation and gives less control over `send`. A dependency can't see the final status and must be added per route.

**Who is the actor on pipeline events?**
The decision-maker: `system:pipeline`. The submitter is on the correlated request row. "Model missed it" vs "human dismissed it" need different remedies.

**What isn't logged?**
Passwords and tokens; the attempted username only as an HMAC; no note text, comments, query strings or raw paths. OWASP logging guidance plus data minimisation.

**Cost and scale?**
One indexed insert per request; whole-response buffering. At scale: monthly partitions, a retention policy with the DPO, streaming to a SIEM.

**With real data?**
Insert-only DB role, a hash chain or WORM export, `pgaudit` for superusers, alerting (reuse, 403 bursts, unusual reads), and audit data in subject access responses.
