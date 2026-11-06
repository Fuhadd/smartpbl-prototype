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
