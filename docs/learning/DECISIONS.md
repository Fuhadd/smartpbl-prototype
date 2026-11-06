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
