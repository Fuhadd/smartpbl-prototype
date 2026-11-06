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
