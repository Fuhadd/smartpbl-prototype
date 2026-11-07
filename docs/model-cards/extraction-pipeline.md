# Model card: care-note risk extraction pipeline (SMARTPBL Tier 1)

Structure follows Mitchell et al., *Model Cards for Model Reporting* (2019). The card describes the **pipeline**, not just the LLM: redaction, extraction, a rules safety net, evidence grounding and routing to human review work together, and are evaluated together. **Evaluated on synthetic notes only; not validated for real care records.**

## Model details

| | |
|---|---|
| Pipeline | Presidio PII redaction (spaCy `en_core_web_lg` + UK recognisers) → LLM extraction into a Pydantic JSON schema → rules baseline → evidence grounding → routing policy |
| LLM | `llama3.1:8b` via Ollama, run locally. Model digest `46e0c10c039e`, recorded on every extraction and audit event |
| Decoding | Schema-constrained decoding (the `Extraction` JSON schema is passed as `format`), temperature 0, seed 42, 4,096-token context, 60 s timeout, one retry on a validation failure |
| Prompt | `prompts/extraction/v2` (sha `132928aea6e4`). The version and SHA-256 are stored with each extraction |
| Rules baseline | `rules-v1`: regex and keyword patterns with negation handling (`app/nlp/baseline.py`) |
| Output | Per note: risk flags (category from a 7-item taxonomy, severity, verbatim evidence, confidence), medication status, `follow_up_required` and a summary. Each flag is either auto-accepted or queued for review with reasons |
| Code | `app/nlp/` (`redact`, `extract`, `baseline`, `ground`, `route`, `pipeline`, `review`); evaluation in `scripts/eval.py` |
| Owner, date | SMARTPBL prototype (KTP application portfolio), 2026-11 |

## Intended use

- **Primary use:** prioritise human attention. The pipeline surfaces possible falls, medication issues, nutrition/hydration, skin integrity, mood/behaviour change, safeguarding concerns and missed/late visits in carers' notes. A coordinator reviews each one, with the evidence highlighted in the note.
- **Primary users:** care coordinators and managers, through the review queue.
- **Decision rights:** a person decides. High-severity and safeguarding flags always go to review; nothing changes a care plan automatically.

## Out-of-scope uses

- **Replacing reading the notes, or the provider's incident and safeguarding procedures.** A missed flag must never mean a missed concern; existing processes stay primary.
- **Clinical diagnosis,** or any judgement about a client beyond "this note may describe a risk".
- **Assessing carers' performance** from their notes.
- **Sending note text to third-party AI services.** The design depends on local inference.
- **Real records** without a DPIA, a fresh evaluation on real notes and clinician-agreed labels (see `docs/DATA_PROTECTION.md`).

## Factors

- **Writing style:** shorthand, typos, lowercase, abbreviations, negation ("no signs of falls"), several risks in one note, and phrasings not seen in development. All of these are measured as slices below.
- **Not measured:** dialect, non-native English, very long notes, voice-to-text artefacts, and risks implied across sentences. Real notes will contain all of these.

## Metrics

- **Recall first.** For safety flags, a missed risk (false negative) costs more than an extra review (false positive). Recall and "high-severity escapes" are therefore the headline metrics, with precision, F1 and severity agreement alongside.
- **Pipeline metrics:**
  - the share of notes sent to review (coordinator workload);
  - gold flags with no flag at all (escapes);
  - auto-accepted false positives (wrong flags that skipped review);
  - schema validity and grounding rate.
- Matching is per note and category. A failed extraction counts as no flags. Bootstrap 95% CIs use 1,000 resamples of notes, seed 42.

## Evaluation data

- **Data:** 40 held-out synthetic notes with 56 gold flags (8 per category), from `scripts/generate_notes.py` with seed 42. See `data/care_notes/DATA_CARD.md`.
- **Separation:** the test split was opened once, after all prompt and rule tuning on the dev split.
- **No training:** the LLM is used zero-shot, with no fine-tuning on these notes.

## Quantitative analyses (synthetic, test split)

| System | Precision | Recall (95% CI) | F1 (95% CI) | Severity agreement | p50 latency |
|---|---|---|---|---|---|
| llama3.1:8b + prompt v2 | 0.960 | **0.857** (0.776–0.930) | **0.906** (0.847–0.955) | 0.81 | 5.8 s |
| Rules baseline | 0.977 | 0.768 (0.642–0.885) | 0.860 (0.777–0.933) | 0.98* | 0.4 ms |
| LLM ∪ rules (recall only) | | 0.929 | | | |

| Deployed pipeline | Value |
|---|---|
| Notes sent to review | 20 / 40 (50%) |
| Gold flags with no flag at all | 4 / 56 (7.1%) |
| High-severity flags escaped | **0 / 19** |
| Auto-accepted false positives | 0 / 27 |
| Schema-valid on first try | 40 / 40 |
| Evidence grounded | 100% |

**Per-category recall (LLM):**
- Weakest: medication **0.62** and mood **0.75**.
- Strongest: skin integrity 1.00 and safeguarding 1.00 (safeguarding precision is 0.80).
- **Slices:** recall on unseen phrasings is 0.81 (rules 0.59), on negation 0.83, and on noisy text 0.85. There was 1 negation false positive among 16 negated mentions.

\*The rules' severity agreement is inflated: the same author wrote the rules and the gold labels. Full tables: `docs/results/tier1_eval_test.md`.

## Ethical considerations

- **Privacy:** names, addresses, postcodes and phone numbers are masked before the LLM sees the text, and the API and UI show only redacted text. Audit rows store HMAC hashes of inputs, not text.
- **Hallucination:** every flag must quote the note. Ungrounded quotes are rejected, and fuzzy matches (score ≥ 90, at least 3 words) go to review.
- **Automation bias:** coordinators may over-trust auto-accepted flags or under-read unflagged notes. The UI shows the evidence and the review reasons, and the model card and training must say plainly that the pipeline misses things.
- **Missed risks fall unevenly:** 3 of the 4 escapes in testing were concealed medication, subtle mood change and a shortened visit. These are quiet signals, not dramatic ones.
- **Carers can override:** the carer app's urgent-concern switch forces review, whatever the models find.

## Caveats and recommendations

- **Optimistic numbers:** the notes are synthetic and template-based, written by the same person who wrote the prompts, rules and labels.
- **Spent test set:** 40 notes give wide CIs, and any further tuning needs a new held-out set.
- **Uninformative confidence:** the LLM's self-reported confidence clusters at 1.0, so routing relies on policy, grounding and the rules safety net, not on the 0.7 confidence threshold.
- **Grounding's limit:** it proves a quote exists, not that it supports the flag. A misread negation can still pass.
- **Smaller-model fallback:** `qwen2.5:3b` found about half the risks (recall 0.50), so it is not a drop-in replacement without its own prompt work.
- **Before real use:** re-evaluate on real, consented, pseudonymised notes with clinician-agreed labels. Monitor recall by category in production with periodic double-reading samples, and re-run the evaluation whenever the model, prompt or redaction changes (all three are versioned in the audit log).
