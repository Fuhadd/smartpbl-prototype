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
