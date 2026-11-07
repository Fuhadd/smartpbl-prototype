# Interview Prep: final pack (KTP Associate, BCU × PBL Care)

**Interview:** 9 December 2026. **How to use this pack:**
1. Read **Part A** (system-level) and **Part B** (KTP) until you can answer each question in your own words in under 90 seconds.
2. Skim the **must-know 20** before the interview.
3. Use **Part D** (the per-step bank) for depth on anything the panel probes.
4. For practice, ask Claude for **mock-interview mode** (Part C).

Every answer below is backed by a file in this repo: README, `docs/DATA_PROTECTION.md`, `docs/model-cards/`, `docs/SECURITY.md` and the learning notes.

**Contents:**
- [Must-know 20](#must-know-20)
- [Part A: system-level questions](#part-a-system-level-questions)
- [Part B: KTP context](#part-b-ktp-context)
- [Part C: mock-interview mode](#part-c-mock-interview-mode)
- [Part D: per-step bank](#part-d-per-step-bank), by tier

---

## Must-know 20

| # | Question | Where the answer is |
|---|---|---|
| 1 | Explain SMARTPBL in a minute to a care manager | 6.1 below; README "The problem" |
| 2 | Walk us through the architecture end to end | A1 |
| 3 | Why a local LLM, not a hosted API? | Setup; A6 |
| 4 | How do you stop the LLM hallucinating flags? | 1.6 (grounding); model card |
| 5 | Which metric matters most for safety flags, and why? | 1.9 (recall first; 0/19 high-severity escapes) |
| 6 | How was the NLP evaluated, and what doesn't it show? | 1.9; A4 |
| 7 | What is a VRPTW and how does OR-Tools solve it? | 2.3 |
| 8 | How does a manager choose between travel and continuity? | 2.4 (Pareto curve, presets) |
| 9 | Why gradient boosting over logistic regression, and how sure are you? | 3.2 |
| 10 | What does SHAP tell you, and what doesn't it? | 3.3, 5.4 |
| 11 | How do you stop the attrition model being used punitively? | 3.3, 5.4, 6.2 |
| 12 | Lawful basis for care notes and for attrition scoring | 6.2 |
| 13 | How is access controlled? What is BOLA? | 4.1, 5.6a |
| 14 | Why is the audit log append-only, and why hashes? | 1.7, 4.2 |
| 15 | What happens when the LLM is down? | A5 |
| 16 | How would this scale to all of PBL's notes and branches? | A2 |
| 17 | What would you do in the first 3 months with real PBL data? | A3, B3 |
| 18 | Why React for coordinators and Flutter for carers? | 5.6b |
| 19 | What are the three-way benefits of this KTP? | B1 |
| 20 | How will you make sure knowledge stays with PBL after you leave? | B2 |

---

## Part A: system-level questions

**A1. Walk us through the architecture end to end.**
Two clients sit on one FastAPI backend: a React dashboard for coordinators and managers, and a Flutter carer app. A care note goes through this pipeline:
1. PII redaction (Presidio with UK recognisers).
2. A local LLM (llama3.1:8b on Ollama) constrained by a JSON schema, with a rules baseline alongside it as a safety net.
3. Grounding: every flag's quote must be found in the note.
4. Routing: high-severity, safeguarding and uncertain flags go to the review queue.

Coordinators approve, edit or reject; the decision is stored with a diff, and everything is written to an append-only audit log in Postgres. Scheduling is an OR-Tools VRPTW with a continuity weight, and every assignment is explained. Attrition risk is gradient boosting on working conditions from those schedules, explained with SHAP and served for support only. Every route is behind JWT roles with least privilege, audited by middleware and rate-limited. The demo runs on Vercel, Cloud Run and Neon, all in UK regions.

**A2. How would it scale to all of PBL's branches?**
- **Ingestion:** move note processing to a job queue (Redis or Postgres-backed). The carer gets an instant "saved", and the queue fills as the LLM works. Run several inference workers on a GPU server inside PBL's network; an 8B model on one modern GPU handles thousands of notes a day.
- **Database:** add a priority column so the queue is sorted and paged in SQL, partition the audit log by month, and use read replicas for dashboards.
- **Scheduling:** solve per branch (routing is local), on a schedule, with solver jobs off the request path.
- **Rate limits and the model cache:** move to Redis so the API can run more than one instance.
- **Tenancy:** scope every query by branch or patch, for both performance and least privilege.

**A3. What's your plan for moving to real PBL data?**
1. **Governance first:** a DPIA, a data-sharing agreement with BCU, Caldicott and DPO sign-off, and updated privacy notices. Consult staff on the workforce module.
2. **Data:** a pseudonymised extract of historic notes. Senior carers or clinicians label a stratified sample with agreed severity definitions; measure inter-rater agreement before trusting the labels.
3. **Baseline:** measure today's process (how many risks are found, and how fast) so improvement is measured against reality, not against my rules.
4. **Evaluate, then tune:** run the existing pipeline unchanged on a held-out set first (honest starting numbers), then tune prompts and rules on a separate dev set.
5. **Shadow mode:** run alongside current practice for weeks, compare, then pilot in one branch with a rollback plan.

**A4. How would you evaluate with real data, and what would make you stop?**
- **Primary metric:** recall on high-severity and safeguarding categories, with confidence intervals and per-category breakdowns. Coordinator workload (the share of notes sent to review) is the cost side.
- **Slices:** dialect, non-native English, voice-to-text and long notes.
- **Production monitoring:** periodic double-reading samples to estimate misses.
- **Stop criteria, agreed with PBL beforehand:**
  - any category with high-severity recall below the agreed threshold;
  - review workload above what coordinators can absorb;
  - evidence that staff trust the flags more than they should (automation bias).

**A5. What are the failure modes, and what happens in each?**

| Failure | What happens |
|---|---|
| LLM down or slow | The note is saved with the rules' flags and sent to review as a failed extraction; nothing is lost |
| Schema-invalid output | One retry, then treated as a failure |
| Invented quote | Grounding rejects it |
| Missed risk | The rules safety net, the carer's urgent switch, and coordinators still read notes |
| Solver timeout | The best partial rota, with a reason for each unassigned visit |
| Database or audit write fails | Reads fail closed: data isn't returned if its access can't be audited |
| Token theft | Refresh-token reuse detection revokes the whole session family |
| Carer loses signal | The note stays in the app; idempotent ids prevent duplicates on retry |

**A6. What are the main ethical risks, and how are they handled?**

| Risk | How it's handled |
|---|---|
| **Privacy** of health data | Redaction, local inference, minimisation, an audit of every read |
| **Automation bias** | Evidence shown with every flag, review reasons given, staff told the pipeline misses things |
| **Punitive use of attrition scores** | Prohibited in the model card, supportive actions only, audited, managers only. Consultation and policy are still needed |
| **Proxy discrimination** (age via tenure) | Age excluded and audited. The controls sit on use: support for new starters is fine, adverse action is not |
| **Accountability** | Every decision has a named human and an audit trail |

**A7. What would you do differently if starting again?**
- **Hold out a second test set from day one:** the Tier 1 test set is now spent.
- **Generate synthetic notes with a second author or model,** to reduce the circularity of one person writing data, rules and labels.
- **Put notes on a job queue from the start,** rather than the synchronous endpoint.
- **Build the coordinator view of a carer's day** alongside the carer `/me` routes.

None of these changes the architecture. They're about evaluation hygiene and operations.

**A8. What are you proudest of, technically?**
The scheduling evaluation. It doesn't just run OR-Tools: every solution is re-checked by an independent checker, a CP-SAT relaxation proves the lower bound on unassignable visits, and continuity is presented as a priced trade-off a manager can choose from. It turns an optimiser into a decision tool.

---

## Part B: KTP context

**B1. What are the three-way benefits of this KTP?**
- **PBL Care (business partner):** an in-house AI capability, aimed at safer care (risks surfaced faster), more efficient rotas (less driving, better continuity) and better retention. Everything is built under PBL's data governance, and ownership of the code and know-how stays with PBL.
- **Birmingham City University (knowledge base):** a real-world testbed for applied AI in social care, with research outputs (evaluation of LLMs on care notes, fairness in workforce analytics), teaching cases and impact evidence. KTP knowledge bases typically generate new research projects and papers from each partnership.
- **Me (associate):** leading a strategic project end to end, with academic supervision, a dedicated development budget and a route into a permanent role. Innovate UK reports that about 75% of associates are offered permanent positions with their business partner.

**B2. How will you make sure knowledge transfers, rather than leaving with you?**
This prototype already shows the habits:
- one learning note per step, an ADR log and model cards;
- a README written for newcomers;
- tests and CI that make changes safe.

At PBL I'd add:
- pairing sessions and short training for coordinators (reading flags, automation bias), managers (reading workforce risk supportively) and IT (operating the stack);
- a runbook for failures and model updates;
- a quarterly evaluation ritual someone else can run.

The measure of success is that PBL can re-run the evaluation and change a prompt without me.

**B3. What would your first 3 months look like?**
- **Month 1:** shadow coordinators and carers, map the current note, rota and retention processes, meet the DPO and Caldicott Guardian, start the DPIA, and agree success metrics with PBL and BCU supervisors.
- **Month 2:** a pseudonymised data extract, a labelling protocol with senior carers, and an honest baseline: today's process, plus the existing pipeline run unchanged.
- **Month 3:** tune on a dev set, prepare shadow mode for the notes pipeline in one branch, and report findings to the KTP Local Management Committee.

Scheduling and workforce work follows once the data and governance foundations are in place.

**B4. How would you use the development budget (about £4,000)?**
Innovate UK gives each associate a dedicated training and development budget. Universities describe it as about £2,000 a year, so about £4,000 over a two-year KTP; I'd confirm with BCU's KTP office. I'd split it roughly as:
- **About 40%: applied ML in production.** LLM evaluation and MLOps (monitoring, model versioning, deployment on GPU infrastructure), because that's the step from prototype to service.
- **About 25%: data protection and AI governance.** A recognised data-protection qualification and ICO/AI-assurance courses, because health data and employee profiling are this project's main risk.
- **About 20%: a conference.** One UK conference such as PyData London or a health and social care AI event, to present the evaluation and bring ideas back.
- **About 15%: books and courses** on operations research and causal inference, for rota changes and measuring whether interventions help retention.

I'd agree priorities with my academic and company supervisors against the project plan.

**B5. Why this KTP, and why you?**
- **The match:** it combines what I've done for years (production Flutter, FastAPI, Postgres, CI) with what my MSc gave me (ML evaluation) and what this prototype shows I can learn fast (LLM pipelines, OR-Tools, SHAP, data protection).
- **The sector:** care is a sector where careful engineering matters: privacy, human oversight and honest evaluation are the job, not extras.
- **The evidence:** this repository builds all three SMARTPBL innovations, with documented decisions and limitations.

**B6. What's the biggest risk to the KTP itself, and how would you manage it?**
- **The risk:** that real notes are harder than synthetic ones, and early results disappoint.
- **The management:** set expectations from the start (synthetic results are a design proof, not a forecast), agree stop or pivot criteria in advance, and deliver value early through the parts that need less data. Scheduling and continuity analytics can show benefit from rota data alone.
- **The second risk:** staff trust. Involve carers and coordinators from month one and never ship a workforce feature without consultation.

---

## Part C: mock-interview mode

When I ask Claude for **mock-interview mode**:
1. **One question at a time.** Claude picks from Part A, Part B and the must-know 20, mixed with probing follow-ups from Part D, at the level of a technical panel (one academic, one company lead, one KTP adviser).
2. **Claude waits for my answer** and doesn't show the model answer first.
3. **Critique:** what was strong, what was missing compared with the model answer, any technical inaccuracy, and length (aim for 60–90 s, and 3–6 sentences for technical answers). Then one sentence to add next time.
4. **A follow-up the panel would plausibly ask,** then continue.
5. **After 8–10 questions:** a summary of weak areas, with the notes to re-read.

---

## Part D: per-step bank

The questions below were written step by step during the build. Each learning note (`docs/learning/NN-*.md`) has the full 5–8 Q&As for its step.


### Setup / Infrastructure

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

### 4.3 Security review

**Walk me through the review.**
All ten OWASP API 2023 risks, each with controls, tests and gaps in `docs/SECURITY.md`. Strongest: auth (API2/5), property exposure (API3), LLM consumption (API10). Partial: no per-patch BOLA scoping; per-process limits. Found and fixed three defects.

**The crash?**
Zero carers means zero vehicles, and OR-Tools aborts the process (SIGABRT): one request was a DoS. Fixed in the solver and the API, with regressions. Validate before native code.

**Login brute force without lockouts?**
20/min per IP, 5/min per username, both before Argon2; refused attempts not counted; no permanent lock. Trade-off: one-minute lockout griefing; production: SSO + MFA.

**Why in-memory limits?**
Exact, testable with a fake clock, no infrastructure. N workers give N× the limit, and a restart resets it. Production: Redis token bucket plus gateway limits.

**No cookies: what follows?**
Bearer header, so no CSRF; CORS with an explicit origin list and no credentials. XSS remains the risk: short tokens, rotation, strict CSP. Production: a BFF.

**Secure by default?**
Outside local: refuse public default secrets, short JWT keys and `*` CORS, all reported at once; docs off. Subprocess test proves both outcomes.

**422s echoing data?**
FastAPI's default includes `input` (note text = health data). A custom handler returns `loc`/`msg`/`type` only.

**Next with real data?**
Patch scoping, Redis limits, TLS and proxy headers, a vault for secrets with key ids, `raw_text` encryption, scheduled scans, a pen test, a DPIA.

### 4.4 Containers and CI

**Container setup?**
Two-stage uv build; the runtime has only the venv and source, a non-root user and a healthcheck. Compose: db healthy → migrate exits 0 → api, read-only, no capabilities, bound to localhost. Ollama on the host for the GPU.

**Why a separate migration job?**
Replicas would race on `alembic upgrade`; serving shouldn't mix with schema changes. The API starts only after the job succeeds; a failure halts the rollout.

**What does CI guarantee?**
Lint, the full suite on real Postgres (a missing DB fails), a vulnerability scan, and an image build, all on locked versions with a read-only token and SHA-pinned actions. Not the real LLM: those tests are opt-in.

**Why SHA-pin actions?**
Tags are movable; a compromised action repo can retarget them. SHAs are immutable (GitHub's secure-use guidance).

**2.3 GB image?**
The ML stack and the spaCy `lg` model. Shrink by: the `md` model (re-check recall), training out of the API, then distroless.

**With real data?**
A private registry with signed, scanned images; vault secrets; TLS at the proxy with `FORWARDED_ALLOW_IPS`; managed UK-region Postgres; Ollama on a private GPU node; staged rollouts gated on migrations; readiness probes.

## Tier 5 — Coordinator dashboard and carer app

### 5.1 Dashboard architecture

**Architecture?**
Vite + React 19 + strict TS; React Router; TanStack Query; Tailwind + shadcn/ui carrying the design tokens. A typed client generated from the API's OpenAPI schema (drift caught in pytest and CI). In-memory tokens, one fetch wrapper, refresh once on 401. Role-aware rail and guards; the API is the gate.

**Why generate the client?**
One contract, two codebases: an API rename becomes a TS compile error. Schema export test + regenerate-and-diff CI step.

**Single-flight refresh?**
Refresh tokens are single use with reuse detection; parallel 401s refreshing separately would look like theft and end the session. One shared promise; mutation-tested.

**Carer vs workforce page?**
Rail hides it (usability), the guard shows denial (UX), the API returns 403 and audits (security). The guard still calls the API, so "recorded in the audit log" is true.

**Reload signs out: why?**
Tokens in memory can't be read from storage by XSS; cookies need CSRF and credentials mode. Production: a BFF with an httpOnly session cookie.

**Design vs backend disagreement?**
Asked, with a recommendation; found the model card already named coordinators; one-line permission change, matrix rows, ADR-029; reads stay audited.

**With real data?**
SSO (OIDC + PKCE), a BFF, branch scoping in the UI, PII-scrubbed error tracking, a strict CSP, a WCAG 2.2 AA audit.

### 5.2a Care-note review screen

**Walk me through it.**
Queue (severity filter) | redacted note with evidence highlighted by category, beside the AI extraction (model, prompt, latency, severity as text and colour, confidence, grounding) | why routed (from server reasons), safety checks, approval route, decision buttons. Stage edits per flag, decide the whole note atomically, go to the next.

**Why a note-level endpoint?**
The act is "decide this note"; per-flag calls can half-apply. One transaction, decisions must cover exactly the pending flags, any invalid edit rolls back all; per-flag diffs and audit events are kept.

**Highlight accuracy?**
Uses the grounding step's stored offsets, not a browser search; highlight first, then render placeholders; drop overlapping or invalid spans.

**Escalation rule?**
High severity only (design rule). The UI shows the button only while a kept flag is high; the API independently returns 409 otherwise and applies nothing.

**Why not the LLM summary as the title?**
In real testing it was three lines with a raw `<PERSON>` token. A deterministic headline from top flag + visit time matches the design and keeps AI text inside the AI panel.

**With real data?**
A care-manager sign-off queue, PBL's real protocols, server-resolved display names under access control, routing policy exposed by the API, user testing of the edit flow.

### 5.2b Overview panels and audit log

**Walk me through it.**
`GET /overview` gives one snapshot for every overview panel: review counts plus "needs attention" from the queue's own sort, flags by category and pipeline health over 7 days, the latest rota against a greedy baseline, and the elevated-risk count. The audit screen is a projection of the append-only log: raw rows grouped into note submitted / AI output / human decision / schedule run / access denied, each listing its source row ids, keyset-paged, filterable, searchable and exportable to CSV.

**Why a projection, not display rows?**
One source of truth. Display rows could disagree with the evidence and couldn't be corrected in an append-only table. A projection writes nothing, and fixing it fixes every past entry. Row ids keep it traceable.

**Why keyset pagination?**
The log only grows, so `id < cursor` gives pages that never shift. OFFSET would repeat or skip rows as new events arrive, and gets slower with depth. Paging over anchors means a group can't be split.

**"vs manual" became "vs greedy baseline". Why?**
There is no manual rota, and an invented figure would be dishonest. Greedy is the documented stand-in, run on the same day and matrix. Caveat: it can serve fewer visits, so with PBL data I'd compare travel per visit served against historical rotas.

**Why audit the overview?**
It quotes note evidence and names a carer from a profiling model. Every disclosure is recorded whichever screen shows it, or the overview becomes the untraced path.

**CSV injection?**
Exported cells starting with `=` `+` `-` `@` (or control and full-width lookalike characters) would run as formulas in Excel. They get a leading apostrophe, following OWASP.

**Relative risk bands?**
Elevated = top 20 % (support capacity from the model card), moderate = above the team average. No calibration claim on synthetic data. The trade-off is that someone is always "elevated", so the wording stays supportive.

**With real data and scale?**
An index or `entry_kind` column for anchors, trigram or full-text search, monthly partitions and retention from the DPIA, patch-scoped access, today's actual rota, and validated thresholds.

### 5.3 Schedule and map

**Walk me through it.**
Carers list (3 pinned in route colours) | Leaflet map with numbered visits and unassigned markers, timeline below | "why this carer" with stored reasons and a next-best counterfactual, and an "Optimise for" panel that previews the Pareto sweep before one real re-solve.

**Why is the map sample-only?**
Runs store a keyed hash of their input, not addresses (data minimisation). The API serves locations only when the hash matches the committed synthetic day. With real data, locations come from the client record under its own access control.

**Why Continuity = 30?**
45 is dominated in the sweep (less continuity, more driving than 30). A test asserts every preset is on the Pareto front.

**Next best?**
The closest other qualified carer from where their route has them; stored at solve time; one-swap, so knock-on effects are ignored. The exact version is a forced re-solve.

**Preview vs live solve?**
Solves take 20 s and are rate-limited, so the preview is instant from the sweep and Apply commits once. The trade-off is fidelity (30 s sweep vs 10 s API solve).

**Greedy comparison on live data?**
Greedy drove 1.1 h less but served 8 fewer visits. Compare at equal coverage, or show coverage beside cost.

**Bug story?**
Postgres `now()` is transaction-scoped; two runs tied, and "latest" was arbitrary. Fixed with wall-clock stamping, caught by a two-run test.

**With real data and scale?**
Patch-scoped access, real names and addresses, self-hosted tiles, OSRM road geometry, dated runs with a real day switcher, a solve job queue, nightly sweeps per patch.

### 5.4 Workforce risk screen

**Walk me through it.**
- A risk list with bands.
- A carer header: score, band, rank.
- Four signal tiles compared with the team median.
- A diverging SHAP bar chart in percentage points that adds up from the baseline to the score.
- Supportive action cards, the use notice, and a model-card panel fed by the API.

**SHAP is log-odds: how are the bars in percentage points?**
Split the probability gap p − p₀ in proportion to each feature's log-odds. The rows add up exactly and keep signs and ranking. It's a convention (the sigmoid is non-linear), stated in the footnote; the exact log-odds stay in the API.

**Why team median instead of trends?**
The data is a snapshot; inventing trends on a screen about people's jobs is wrong. With real data, store weekly snapshots and show both.

**How is punitive use designed out?**
- Actions come only from levers the provider can change that add at least 2 points.
- A check-in is offered only to the top 20%, worded as support.
- The use notice is on every page.
- The label and age are never sent, and every view is audited.
- Policy and training still matter.

**Why a hand-built chart?**
It's twelve bars: a grid of list items gives screen-reader text per row and text alongside every colour, with no library weight.

**Real data and scale?**
- Names behind patch-scoped access, plus carer self-access.
- Feature history; a DPIA and staff consultation (ICO monitoring-workers guidance).
- Paging by band and patch.

### 5.6a Carer app API

**How do you stop a carer reading or writing someone else's data?**
- Reads go through `/me`, with the identity taken from the token.
- Writes check the object: own `carer_ref`, a visit on their own rota, and that visit's client.
- Another carer's visit returns 404, so its existence isn't confirmed.
- Tests tamper with each field.

**Why is "same user id" not enough?**
OWASP API1: the id can be the caller's own while the object (visit, client) belongs to someone else. Check the relationship, not just the identity.

**Carers see other carers' notes?**
Only a handover: clients on today's rota, the last 3 notes, redacted, with rejected flags hidden, and every read audited. Scope would be confirmed with the Caldicott Guardian and the DPIA.

**Urgent switch?**
A human-review trigger independent of the model: it goes to the top of the queue as high priority, and a flag-less note is acknowledged through the audited note decision.

### 5.6b Flutter carer app

**Why Flutter here and React for the dashboard?**
Different users: dense desktop tables for coordinators, and a phone-first app that can become a store app for carers. Both use the same typed API.

**What does `--wasm` give you?**
dart2wasm plus the skwasm renderer, faster and able to use threads with COOP/COEP headers. `flutter_bootstrap.js` falls back to dart2js plus CanvasKit when WasmGC is missing (Safari and Firefox by default).

**Load size?**
Measured at about 2.4 MB gzipped on the Wasm path, against 0.15 MB for the React dashboard. That's acceptable for a daily work tool, since the service worker caches it. It would be wrong for a public one-off page.

**Token refresh with parallel calls?**
A single shared refresh future and one retry. A failed refresh ends the session. `QueuedInterceptor` was avoided because of a deadlock. A test asserts exactly one refresh.

**What if a carer loses signal while sending?**
The note stays in the box. The id is created once per note, so a retry that gets 409 means it was saved and no duplicate is created.

**How did you verify the UI?**
Widget tests at 390×844 with the real Inter font loaded, plus the release build driven in headless Chrome and compared with the designs. That caught two layout bugs.

### 5.7 Demo access

**Public demo passwords?**
A bounded exposure: the data is synthetic, the accounts can only be created in `local`/`demo`, login is rate-limited per user, and every action is audited. Production would use SSO with no seeded accounts.

**Why is the first request slow?**
Cloud Run and Neon both scale to zero. That's fine for a portfolio (warm it up before demoing). For PBL, keep one instance warm during working hours.

**What doesn't the hosted demo show?**
Live LLM extraction, which runs locally by design (data stays on our hardware). The flags shown were produced locally on the same synthetic notes.

## Tier 6 — Packaging

### 6.1 Final README

**SMARTPBL in one minute, for a care manager?**
- It reads visit notes and highlights falls, medication and safeguarding worries for a coordinator to confirm, with the sentence shown.
- It plans rotas that cut driving while keeping familiar carers.
- It shows which working conditions push carers to leave, so they can be fixed.
- People decide everything, and it's all logged.

**Most and least confident result?**
- **Most:** scheduling, which beat greedy on every day, with independent checks and proven bounds.
- **Least:** the absolute NLP numbers (40 synthetic notes written by the same author). The design is validated; real-world performance isn't.

**How do you avoid overclaiming?**
Sample size and seed on every number, confidence intervals, and limitations per tier and overall, all on the front page.

### 6.2 Data protection

**Lawful basis for care notes with AI?**
Article 6 (contract or public task, as for delivering care) plus Article 9(2)(h) with DPA 2018 Schedule 1 condition 2 and a duty of confidentiality. Training on the notes is a further purpose to assess separately. Confirm with the DPO.

**Attrition basis?**
Legitimate interests. Purpose: retention and continuity. Necessity: team-level reporting isn't enough. Balancing: support only, with adverse use prohibited. Consult staff; no solely automated decisions.

**Biggest residual risk?**
Punitive use of attrition scores. It's a policy and culture risk, so it stays Medium despite the controls.

**Erasure vs append-only audit?**
Care records carry retention duties. The audit holds hashes and ids, not content, so it can be retained without re-exposing data.

### 6.3 Model cards

**What's in a model card, and for whom?**
Versions, intended and out-of-scope use, factors, metrics and data (n, seed), results with CIs and slices, ethics, and caveats. It serves users, auditors and DPOs, and future engineers.

**Why a pipeline card for Tier 1?**
Users get the pipeline's output: LLM recall 0.857, but the pipeline lets 0/19 high-severity flags escape and gets union recall of 0.929. LLM-only figures misstate safety and hide that the rules are load-bearing.

**What to monitor?**
Recall by category from double-reading samples, the share sent to review, accuracy of auto-accepted flags, grounding and schema failures, and latency. Re-evaluate on any change to the model, prompt or redaction (all versioned in the audit log).

### 6.4 Demo script

**Three minutes?**
Problem, then one note from carer to coordinator (grounded flag, approve), then schedule reasons and the trade-off, then workforce as support, then audit and limits. See `docs/DEMO_SCRIPT.md`.

**What did you cut?**
Overview, audit filters and CSV, charts and security. They don't change the story and are one click away.

**Model gets it wrong live?**
Use it: that's why people review every flag, why there's a rules safety net, and why carers have the urgent switch.
