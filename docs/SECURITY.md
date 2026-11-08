# SMARTPBL security review

Reviewed against the [OWASP API Security Top 10 (2023)](https://api-security.owasp.org/editions/2023/en/0x11-t10) on 2026-11-07, at the end of Step 4.3. The scope is the FastAPI backend: care-notes NLP, carer matching, workforce risk, auth and audit. **Everything runs on synthetic data.** This is a prototype review, not a penetration test.

Status key: **Addressed** = implemented and tested. **Partial** = mitigated, with a known gap. **Open** = not yet done, with a plan.

## Summary

| # | Risk | Status | Main controls | Tests |
|---|---|---|---|---|
| API1 | Broken Object Level Authorization | Partial | Role checks on every route; carers can't read records at all; no per-patch scoping yet | `test_auth_api.py` matrix |
| API2 | Broken Authentication | Addressed | Argon2id, pinned-HS256 JWTs with required claims and a type claim, 15-min access tokens, rotating refresh tokens with reuse detection, uniform 401s, login rate limits per IP and per username | `test_security.py`, `test_auth_api.py`, `test_security_hardening.py` |
| API3 | Broken Object Property Level Authorization | Addressed | Explicit response models; raw note text, the attrition label and age band never returned; 422s don't echo input; `extra="forbid"` on request bodies | `test_api.py`, `test_workforce_api.py`, `test_security_hardening.py` |
| API4 | Unrestricted Resource Consumption | Addressed (per process) | 1 MB body limit (declared or chunked); id patterns and length caps; scenario caps; solver time cap; paging caps; per-user limits on LLM and solver calls | `test_security_hardening.py` |
| API5 | Broken Function Level Authorization | Addressed | Deny by default: a permission per route from one role → permission table; guard test, independent route × role matrix, coverage test | `test_auth_api.py` |
| API6 | Unrestricted Access to Sensitive Business Flows | Partial | Rate limits on solver runs and note submission; every workforce-risk view audited; coordinators and managers only (ADR-029) | `test_security_hardening.py`, `test_audit_middleware.py` |
| API7 | Server Side Request Forgery | Addressed | No user-supplied URLs; OSRM and Ollama addresses come from server settings only | n/a (by design) |
| API8 | Security Misconfiguration | Partial | Refuses to start outside local with default secrets, a short JWT key or `*` CORS; security headers; strict CORS; docs off outside local; no stack traces to clients. Open: TLS termination and the `server` header (Step 4.4 container) | `test_security_hardening.py` |
| API9 | Improper Inventory Management | Partial | One API version; OpenAPI is the single route inventory (the guard tests read it); docs hidden outside local. Open: versioned paths, deprecation policy | `test_auth_api.py` |
| API10 | Unsafe Consumption of APIs | Addressed | LLM output: schema-constrained decoding, Pydantic validation, one retry, timeout, evidence grounding, human review. OSRM output: status and unroutable pairs checked, cached, haversine fallback | `test_extract.py`, `test_ground.py`, `test_travel.py` |

## Detail by risk

### API1: Broken Object Level Authorization
- **Done:**
  - Every route needs a permission (ADR-025).
  - Carers can only *create* notes; they can't read any note, schedule or risk score back.
  - Object ids are random UUIDs (notes, flags, runs), so guessing them gives an attacker nothing.
- **Gap:** coordinators and managers can read *every* note and schedule, with no scoping by branch or patch. Real PBL data needs object-level checks: each user linked to a patch, and every query filtered by it. The same mechanism lets carers read their own notes and attrition explanation (right of access).

### API2: Broken Authentication
- **Passwords:** Argon2id (m = 64 MiB, t = 3, p = 4) via pwdlib, minimum 12 characters, no self-registration.
- **Tokens:** HS256 pinned (`alg: none` and HS512 forgeries rejected). Required claims are `exp, iat, iss, aud, sub, jti, type`, and the type claim stops refresh tokens being used as access tokens. The user is reloaded on every request, so disabling an account takes effect immediately.
- **Refresh tokens:** single use. Reuse revokes the whole family and writes a `refresh_token_reuse_detected` audit event.
- **Brute force:** at most 20 login attempts per IP and 5 per username per rolling minute, checked *before* the Argon2 work, so the limiter can't itself be used to tie up the CPU. Refused attempts aren't counted, so a user who waits gets back in.
- **Known trade-off:** the per-username limit lets someone lock a known username out of login for up to a minute at a time. That's acceptable for staff accounts with SSO planned; an IdP would add MFA and adaptive lockout.

### API3: Broken Object Property Level Authorization
- Responses are explicit Pydantic models, never serialised ORM rows. Raw note text is stored but never returned (only redacted text). The workforce responses omit the label and the age band, and a test scans the raw JSON.
- Request bodies use `extra="forbid"`, so a client can't set fields like `review_status` (mass assignment).
- **Fixed in 4.3:** FastAPI's default 422 echoed each invalid field's submitted `input`, which for a note is health data. A custom handler now returns `loc`, `msg` and `type` only.

### API4: Unrestricted Resource Consumption
| Resource | Limit |
|---|---|
| Request body | 1 MB (`SMARTPBL_MAX_BODY_BYTES`): 413, even for chunked bodies with no `Content-Length` |
| Note | text ≤ 5,000 chars; ids `^[A-Za-z0-9_.-]{1,50}$` |
| Scenario | ≤ 60 carers, 200 clients, 400 visits, 10 preferred/recent carers per client, name ≤ 100 chars; at least one carer |
| Solver | `time_limit_s` ≤ 30 (two-phase: ≤ 60 s per request); 3 solves per user per minute |
| LLM | 60 s timeout, one retry; 30 notes per user per minute |
| Paging | `limit` ≤ 200 on lists |

- **Fixed in 4.3 (found by this review):**
  - An 80-character `note_id` passed validation and failed in the database with a 500, *after* spending an LLM call.
  - **A scenario with zero carers made OR-Tools abort the whole process (SIGABRT): one request could take the API down.** The solver now raises a Python error first, the API returns 422, and both have regression tests.
- **Gap:** limits are in-memory and per process. With N workers the effective limit is N×, and a restart resets it. Production: a shared store (Redis) or the API gateway. Long solves should move to a job queue (backlog).

### API5: Broken Function Level Authorization
Deny by default, as described in ADR-025. One table maps roles to permissions:
- **Carer:** create notes.
- **Coordinator:** notes, review decisions, solver.
- **Manager:** audit trail, workforce risk, read-only operations.

Since ADR-029 (Tier 5 designs), coordinators can also read the audit trail and workforce risk.

Authentication runs at router level before any endpoint dependency. Three tests keep the policy honest:
- **Guard test:** every non-public operation in the OpenAPI schema has bearer security and a `require(...)`.
- **Matrix test:** an independently written route × role table is checked against every role.
- **Coverage test:** the matrix lists every route.

Mutation-tested.

### API6: Unrestricted Access to Sensitive Business Flows
The sensitive flows are bulk reading of workforce risk (profiling employees), mass note submission (LLM cost) and solver runs (CPU). Controls:
- workforce risk is limited to coordinators and managers (never carers), every view is audited with the carers shown, and list pages are capped;
- per-user limits on solver runs and note submission.

**Gap:** no anomaly alerting yet (e.g. one manager opening every carer's explanation); see BACKLOG.

**Step 5.2b additions:**
- **`GET /overview`** audits what it discloses, as the queue and the risk list do: the notes whose evidence it quotes (`review_queue_viewed`) and the carer it names (`workforce_risk_viewed`).
- **The audit timeline, summary and export** (`audit.read`, coordinators and managers) are reads of the log and are themselves recorded by the middleware.
- **The CSV export** is bounded (5000 entries) and neutralises formula cells. Cells starting with `=` `+` `-` `@`, tab, CR or LF, or their full-width forms, get a leading apostrophe ([OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection)).
- **Search input** is capped at 100 characters, and `%`, `_` and `\` are escaped before `ILIKE`, so a query can't become a wildcard scan.

**Step 5.3 additions:**
- **`GET /schedule/{run_id}/map`** serves locations only for runs whose input HMAC matches the committed synthetic sample. Runs still store no locations.
- **The dashboard loads map tiles from `tile.openstreetmap.org`,** a third party that sees which map areas are viewed. That is acceptable for synthetic demo data; production needs self-hosted or contracted tiles. The 5.5 CSP must allow this `img-src`.

**Step 5.6a additions (API1, Broken Object Level Authorization):**
- **Carer reads:** these use `/me/visits` and `/me/visits/{visit_id}`, which take the carer from the token, so there is no carer id in the URL. Another carer's visit is a 404, so the response doesn't confirm it exists.
- **Carer writes:** `POST /notes` from a carer must name their own `carer_ref`, a visit on their current rota, and that visit's client. Otherwise it gets a 403. Tests tamper with each field.
- **Handover notes:** carers can read only the last 3 redacted notes, for clients on today's rota. Each read is audited (`client_notes_viewed`, subject `visit`).

**Step 5.4 additions:**
- **Workforce responses add only derived, non-identifying fields:** `points` and `team_value`. The team value is a median across 200 carers, which reveals no individual. The label and age band are still never sent (an existing test still checks this).
- **The workforce list loads the whole current workforce (200)** in one audited read, so the `workforce_risk_viewed` event lists every ref shown. Paging by patch is in the backlog, for least privilege at real scale.

### API7: Server Side Request Forgery
The API makes two kinds of outbound request: to Ollama (`SMARTPBL_OLLAMA_BASE_URL`) and to OSRM (`SMARTPBL_OSRM_BASE_URL`). Both are server configuration, never request input. Scenario coordinates are numbers bounded to valid latitude and longitude, and the OSRM request URL is built from them, not from strings. Keep it this way: any future "fetch this URL" feature needs an allowlist.

### API8: Security Misconfiguration
- **Start-up refusal:** outside `SMARTPBL_ENVIRONMENT=local`, the app refuses to start if the JWT secret is the public default or shorter than 32 bytes, if the audit HMAC key is the default, or if CORS includes `*`. It lists every problem at once. A subprocess test proves a "production" start fails with the defaults and succeeds with real secrets.
- **Headers on every response:** `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, following the OWASP REST Security Cheat Sheet. HSTS is added outside local.
- **CORS:** an explicit origin list (Vite dev server and Flutter web dev by default), methods `GET`/`POST`, headers `Authorization`/`Content-Type`, exposes `X-Request-ID` and `Retry-After`. Credentials are disabled, because tokens travel in the `Authorization` header, not cookies (ADR-027).
- **Docs:** Swagger UI, ReDoc and `/openapi.json` exist only in local development.
- **Errors:** unhandled exceptions return a generic 500 (no stack traces). The audit middleware logs the failure server-side with the request id.
- **Open (Step 4.4):** TLS termination at a reverse proxy; run uvicorn with `--no-server-header` and `--proxy-headers --forwarded-allow-ips=<proxy>`, so login rate limits see real client IPs and never trust `X-Forwarded-For` from the internet.

### API9: Improper Inventory Management
One deployment and one version. The OpenAPI schema is the inventory, and the auth guard tests read it, so an undocumented route can't exist without failing CI. **Open:** versioned paths (`/v1`) before any external client is supported, and a deprecation policy.

### API10: Unsafe Consumption of APIs
The LLM is the riskiest upstream: its output is untrusted text that drives safety flags. The controls are:
- schema-constrained decoding;
- Pydantic validation with one retry, plus a timeout;
- grounding: every evidence quote must exist in the note (exact or fuzzy match), or the flag is dropped;
- human review routing for high-severity, low-confidence or ungrounded flags;
- the rules baseline as a safety net when the LLM fails;
- PII redaction *before* the call, so even a compromised model never sees names, addresses or phone numbers.

OSRM responses are rejected unless the status is OK and every pair is routable, then cached, with a haversine fallback.

## Supply chain and static analysis
- **Dependencies:** `uv.lock` pins exact versions and hashes. `pip-audit` 2.10.1 (PyPI advisory database) over all 350 locked requirements found **no known vulnerabilities** on 2026-11-07. The spaCy model wheel is installed from its GitHub release URL and isn't covered by `pip-audit`. Re-run with:

  ```bash
  uv export --format requirements-txt --no-hashes --no-emit-project | grep -v en-core-web-lg > /tmp/reqs.txt
  uvx pip-audit -r /tmp/reqs.txt
  ```
- **Static analysis:** ruff's flake8-bandit rules (`S`) are enabled for the whole repo. Every finding outside tests was triaged as a false positive: the OAuth `"bearer"` token type, an event name, seeded RNG for synthetic data and bootstrap resampling, and type-narrowing asserts in offline scripts. Each is suppressed with a reason. CI (Step 4.4) will run both.

## Secrets management
- **Secrets:** the JWT signing key and the audit HMAC key, both read from the environment (`SMARTPBL_*`) via pydantic-settings, as `SecretStr` so they don't appear in reprs or logs.
- **Never committed:** `.env` is git-ignored, `.env.example` holds placeholders, and pre-commit runs `detect-private-key`.
- **Rotation:**
  - **JWT key:** rotating it logs everyone out, which is acceptable.
  - **Audit HMAC key:** rotating it breaks hash comparisons with older rows. Record a key id with each hash before the first rotation (backlog).
- **Production:** inject secrets from a secrets manager (e.g. Azure Key Vault, given PBL's likely Microsoft estate), never bake them into images.

## Out of scope for the prototype
Penetration testing, DAST scans, infrastructure hardening (network policy, database TLS, at-rest encryption of `raw_text`), MFA (delegated to an IdP in production), and a formal DPIA (Step 6.2).
