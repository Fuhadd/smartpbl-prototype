# Backlog / Future work

- **TestClient deprecation warning:** Starlette warns that `httpx` with `TestClient` is deprecated and suggests `httpx2`. The swap was not made, because the package needs vetting first (maintainer, provenance). Decide before Tier 4 CI.
- **Readiness endpoint:** `/ready` that checks the DB and Ollama connections (Tier 4).
