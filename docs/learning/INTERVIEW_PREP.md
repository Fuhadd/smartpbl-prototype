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
