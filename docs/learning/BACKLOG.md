# Backlog / Future work

- **TestClient deprecation warning:** Starlette warns that `httpx` with `TestClient` is deprecated and suggests `httpx2`. The swap was not made, because the package needs vetting first (maintainer, provenance). Decide before Tier 4 CI.
- **Readiness endpoint:** `/ready` that checks the DB and Ollama connections (Tier 4).
- **CI and the spaCy model:** `en_core_web_lg` is ~400 MB. Cache it in GitHub Actions (Tier 4), or mark the redaction tests and use a smaller model in a fast CI job.
- **Gazetteer integration:** pass client and next-of-kin names from a client registry into `redact(known_names=...)` once persistence exists (Step 1.7+).
- **Consistent pseudonyms within a note** (`<PERSON_1>`, `<PERSON_2>`) if evaluation shows lost relationships hurt safeguarding recall.
- **Project-plan Presidio link** points to `microsoft.github.io/presidio`; the project moved to `presidio.dataprivacystack.org` (verified 2026-11-06).
- **Baseline post-negation** ("Falls: none"): a known gap, left as the 04 exercise.
- **Redaction over-masking in run-on notes:** spaCy tags sentence-initial capitalised words ("Put", "Daughter") as PERSON when notes have no full stops. Consider a minimum PERSON score or a stop-word allowlist.
- **Hybrid extraction:** union the LLM and high-precision rule flags (e.g. the time-comparison late-visit rule) if 1.9 shows they complement each other.
- **Better uncertainty signal:** token log-probs or agreement across samples (n>1 at T>0) instead of self-reported confidence.
- **Missed visit vs safeguarding:** v2 files "no carer attended" under safeguarding. Consider allowing both, or a taxonomy note, after review with PBL.
