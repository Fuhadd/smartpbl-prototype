# SMARTPBL Prototype

A portfolio prototype of an AI platform for domiciliary care. It has three parts:

1. **Care-notes NLP**: a local LLM turns free-text notes into evidence-grounded risk flags, with human review and an audit trail.
2. **Carer matching**: OR-Tools VRPTW that balances travel time against continuity of care.
3. **Attrition prediction**: explainable models that flag carers at risk of leaving.

> **All data is synthetic.** No real people, clients or PBL Care records are used. Results on synthetic data do not show real-world performance.

## Status

- [x] Step 0: setup
- [ ] Tier 1: care-notes NLP (1.1 schemas ✅)
- [ ] Tier 2: carer matching
- [ ] Tiers 3–6: attrition, production layer, Flutter app, packaging

## Quick start

Prerequisites: Python 3.12 (managed by `uv`), Docker, Ollama.

```bash
uv sync                                   # create .venv and install deps
uv run pre-commit install                 # git hooks: ruff + hygiene checks
cp .env.example .env
docker compose up -d db                   # PostgreSQL 16
ollama pull llama3.1:8b                   # default LLM (qwen2.5:3b optional)
uv run pytest                             # tests
uv run uvicorn app.main:app --reload      # API at http://localhost:8000/docs
```

## Layout

Learning notes and the decision log are in [`docs/learning/`](docs/learning/).

## Limitations

Synthetic data only. Developed and tested on one Apple M1 Pro (16 GB) machine. The other sections are filled in as each tier is completed.
