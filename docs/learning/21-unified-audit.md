# 21 — Unified audit

## 1. What was built

| File | Purpose |
|---|---|
| `app/audit/middleware.py` | **Pure ASGI middleware.** Every HTTP request gets a `request_id`, returned as `X-Request-ID`. After each routed API call (not `/health`, docs or unmatched paths) it writes one `api_request` row: actor, method, **route template**, status, duration, and a subject derived from the path parameters. Reads **fail closed**: the response is buffered, and if the audit write fails the client gets a 500 instead of the data |
| `app/audit/context.py` | `RequestAudit` (request id, actor, attempted username), bound to a context variable by the middleware and filled in by the code below it |
| `app/audit/log.py` | `record()` stamps **every** event with the current `request_id` and accepts a generic `subject`. Note events default to the note as subject |
| `app/audit/models.py`, migration `0006` | `subject_type` / `subject_id` (indexed together), `request_id` (indexed), `SubjectType` enum, and three new events: `api_request`, `review_queue_viewed`, `refresh_token_reuse_detected`. Not backfilled (append-only); downgrade refuses if Step 4.2 events exist |
| `app/api/deps.py`, `app/api/auth.py`, `app/auth/service.py` | The authenticated user becomes the request's actor. Login records an HMAC of the attempted username, success or failure. Reuse of a refresh token writes a security event in the same transaction as the family revocation |
| `app/api/review.py` | `GET /review/queue` records which notes' text was shown |
| `app/api/audit.py` | `GET /audit/{note_id}` now answers **"who did what to this note, and who has seen it"**: the note's own events, the requests that caused them (joined by request id), direct reads, and queue views that displayed it |
| `app/matching/service.py`, `app/api/workforce.py` | Subjects on solver runs (`schedule_run`) and explanation views (`carer`) |
| `tests/test_audit_middleware.py` | 11 tests: one row per call with the route template and subject; `/health` and unrouted paths skipped; domain events share the request id of the call; 403s and 401s recorded; login outcomes with a hashed username; the reuse alert; the note trail shows queue views and reads; reads fail closed and writes don't; every path parameter maps to a subject type |

Tests: 301 → **312**. Live check (uvicorn + psql) after a failed login, a successful one, a workforce explanation and a refused solver call:

    api_request                  | anonymous         |         |         | 94750309 | /auth/token                        | 401 | 55bf5e3f
    api_request                  | user:manager.demo |         |         | 1c721981 | /auth/token                        | 200 | d895735f
    workforce_explanation_viewed | user:manager.demo | carer   | WF-0461 | c5691e9e |                                    |     |
    api_request                  | user:manager.demo | carer   | WF-0461 | c5691e9e | /workforce/{carer_ref}/explanation | 200 |
    api_request                  | user:manager.demo |         |         | 4f266786 | /schedule/solve                    | 403 |

The explanation's domain event and its access row share request `c5691e9e`, the value the client received in `X-Request-ID`.

## 2. Why this way

- **Two layers, one log.** Before this step, auditing depended on each endpoint remembering to call `record()`, and only AI decisions and workforce views did. Now:
  - **Access layer (automatic).** The middleware writes one row for every routed call, so no endpoint can forget. It covers OWASP's always-log list: authentication successes and failures, authorisation failures, and access to sensitive data.
  - **Decision layer (explicit).** The pipeline, reviewer, solver and workforce code keep writing semantic events (model version, prompt version, input hash, diff), inside the same transaction as the change.
  - **The request id joins them.** "Which user caused this model decision?" becomes a lookup, and the client can quote `X-Request-ID` in a support ticket.
- **Actor means the decision-maker.** `note_ingested … flags_routed` stay `system:pipeline`, because the model made those decisions. The human who submitted the note is the actor on the correlated `api_request` row. Review decisions are `user:<name>`, because a person decided. Keeping "who decided" separate from "who asked" matters for accountability in a care setting: a falls flag missed by the model and one dismissed by a coordinator are different incidents.
- **Fail closed for reads, not for writes.** For a GET, the data is the risk: if the system can't record who saw a carer's attrition explanation, it doesn't show it. The middleware holds the whole response until the row is committed. A write has already committed its change *and* its domain events atomically, so returning 500 would be false and would invite a duplicate retry. Instead the failure is logged and the real response sent. Tests cover both paths.
- **Pure ASGI, not `BaseHTTPMiddleware`.** Starlette's docs say `BaseHTTPMiddleware` blocks context-variable changes from propagating upward, and recommend pure ASGI middleware instead. The design also needs exact control: buffer the response messages, decide, then send or replace them. That is the ASGI `send` channel itself.
- **Context variable holding a mutable object.** The middleware binds a `RequestAudit` object *before* calling the app. The request's tasks and worker threads inherit a copy of the context, so they see the **same object**. `get_current_user` sets `ctx.actor` on it, which mutates the object rather than rebinding the variable, so the change is visible to the middleware afterwards. A plain `ContextVar.set()` downstream would be invisible upstream; the Python docs' `copy_context()` example shows exactly that.
- **Record the route template, never the raw path or query.** `/notes/{note_id}` plus a typed subject gives a stable, indexable "what", with no free text (query strings can carry search terms). Ids go into `subject_id`, and a test fails if a new path parameter has no subject type.
- **Hash the attempted username.** OWASP's logging guidance says to remove or hash passwords and sensitive data. People do type their password into the username field, so a raw-username column would eventually store passwords. The HMAC (keyed, from Step 1.7) still lets you count failures per account and match a known username, without storing what was typed.
- **No backfill.** Older note events keep `note_id` and have no subject. The trail query matches either. Updating old rows would mean disabling the append-only trigger, and an audit log that gets rewritten whenever the schema changes is worthless as evidence.

## 3. Alternatives considered

| Option | Pros | Cons | When I'd choose it |
|---|---|---|---|
| **ASGI middleware + explicit domain events + request id (chosen)** | Nothing escapes the access layer; decisions keep rich, transactional detail; reads fail closed | Middleware buffers whole responses; a second DB write per request | A JSON API with sensitive reads, like this one |
| Explicit `record()` calls only (before this step) | Simple; all rows transactional with the action | Easy to forget; access to most endpoints was invisible | Very small APIs, or writes only |
| Database triggers / `pgaudit` | Catches every SQL statement, even from admin tools | Knows the DB role, not the app user; no model or prompt context; very noisy | A complement, for DBA and superuser activity (the threat Tier 1 noted) |
| Ship logs to an external SIEM (OpenTelemetry, Loki, Sentinel) | Central search, alerting, retention, tamper resistance off-host | Infrastructure; personal data leaves the system boundary, so DPA terms are needed | Production: stream these same rows out as well, not instead |

## 4. How it works

```mermaid
sequenceDiagram
  participant C as Client
  participant M as AuditMiddleware
  participant R as Router + deps
  participant DB as Postgres
  C->>M: GET /workforce/WF-0461/explanation
  M->>M: ctx = RequestAudit(request_id); bind to contextvar
  M->>R: app(scope, receive, capture)
  R->>R: get_current_user → ctx.actor = "user:manager.demo"
  R->>DB: INSERT workforce_explanation_viewed (request_id, subject carer WF-0461); COMMIT
  R-->>M: buffered: response.start(200) + body
  M->>DB: INSERT api_request (actor, route template, status, subject); COMMIT
  alt audit write fails and method is GET
    M-->>C: 500 "audit log unavailable; response withheld"
  else
    M-->>C: 200 + X-Request-ID + body
  end
```

**ASGI in brief.** An ASGI app is `async def app(scope, receive, send)`. `scope` describes the request: path, method, and, after routing, the matched `route` and `path_params`. The app *sends* messages: `http.response.start` (status, headers), then one or more `http.response.body`. Middleware is an app that wraps another app. By passing its own `capture` function as `send`, it sees every outgoing message and decides what reaches the client.

**Why the route is visible after the call.** Starlette's router writes the matched route and path parameters into the *same* `scope` dict it received, so after `await self.app(...)` returns, the middleware can read `scope["route"].path` (the template). I confirmed this with a 15-line experiment first, because FastAPI 0.162 includes routers lazily (note 20).

**Worked example: "who has seen note N?"**

    names_note = note_id = N
               OR (subject_type = care_note AND subject_id = N)
               OR (event_type = review_queue_viewed AND output @> {"note_ids": [N]})
    trail      = names_note
               OR (event_type = api_request AND request_id IN (request ids of names_note))

For a note submitted by a coordinator, shown in a queue, then opened by a manager, the trail contains:
- the 5 pipeline events and the `POST /notes` row (coordinator);
- the queue view event and its `GET /review/queue` row;
- the manager's `GET /notes/{note_id}` row;
- the manager's own `GET /audit/{note_id}` reads, from the second call onwards.

## 5. Interview questions and answers

**Q1. How is auditing unified across modules?**
Two layers joined by a request id. An ASGI middleware writes one access row for every routed call: authenticated actor, route template, status, duration and a typed subject from the path. So every data access, including refusals, is recorded without each endpoint having to remember. The domain code still writes semantic events for AI and human decisions (model version, prompt version, input hash, reviewer diff) in the same transaction as the change. Every event carries the request's id, which is also returned to the client as `X-Request-ID`, so you can go from a model decision to the person who triggered it, or from a support ticket to the log.

**Q2. What does "fail closed" mean here, and why only for reads?**
For a GET, the middleware buffers the response, commits the audit row, and only then sends the data. If the audit write fails, the client gets a 500 and the data never leaves the server: no unlogged disclosure of health or HR data. For writes, the change and its domain events have already been committed together. Turning that into a 500 would misreport the outcome and invite a duplicate retry, so the failure is logged for operations and the true response is returned. Both paths have tests that break the audit writer on purpose.

**Q3. Why a pure ASGI middleware rather than `BaseHTTPMiddleware` or a dependency?**
`BaseHTTPMiddleware` blocks context-variable changes from propagating upward (Starlette documents this), and it gives less control over the response stream. Pure ASGI lets me intercept the `send` channel, hold the messages, and replace them on failure. A FastAPI dependency could write the row, but it can't see the final status code, and it would need adding to every route. A middleware is the one place every request passes through.

**Q4. Why is the model, not the user, the actor on pipeline events?**
The actor field answers "who made this decision". The flags were produced by the LLM pipeline, so `system:pipeline` is accurate. The submitting coordinator appears on the correlated request row. This distinction matters in an incident review: "the model missed a fall" and "a coordinator dismissed a fall flag" lead to different remedies (retraining or prompt work vs supervision). Review decisions are attributed to the reviewer for the same reason.

**Q5. What do you deliberately not log?**
- **Passwords and tokens:** never logged. The attempted username is HMAC-hashed, because people type passwords into the username box.
- **Free text:** no note text, no reviewer comments (from 1.8), no query strings. Raw paths are replaced by the route template.
- **Subjects:** typed ids, not names.

This follows OWASP's logging guidance on excluding authentication secrets and sensitive personal data, and UK GDPR data minimisation. The audit log has a longer retention than the data, so it must not quietly become a second copy of it.

**Q6. Trade-off: the cost of an extra write per request.**
It's one indexed insert per call on the same database, well under a millisecond against requests that take tens of milliseconds to tens of seconds. The real costs are table growth and the buffering of whole responses. That's fine for JSON responses of a few kilobytes, but it would need rethinking for large exports or streaming. At scale I'd partition `audit_events` by month, set a retention policy agreed with the DPO, and stream rows to a SIEM for alerting rather than querying Postgres.

**Q7. With real PBL data, what changes?**
Tamper evidence beyond the application: separate database roles, so the API can only insert; a hash chain or write-once export; and `pgaudit` for superuser activity. Retention, set with the DPO: perhaps keep access rows for a fixed number of years in line with care-records guidance, then aggregate. Monitoring: alerts on reuse events, bursts of 403s, failed-login spikes and unusual reading patterns, such as one user opening many carers' risk explanations. And a self-service report, so a carer's subject access request can include who viewed their attrition explanation.

## 6. Learn more

**Official documentation**
- Starlette, [Middleware](https://starlette.dev/middleware/): the "Pure ASGI Middleware" section, and the `BaseHTTPMiddleware` limitations on context variables. *The docs moved from starlette.io to starlette.dev.*
- Python, [`contextvars`](https://docs.python.org/3/library/contextvars.html): copied contexts, and why `set()` downstream doesn't reach the caller (hence the mutable context object).
- OWASP, [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): which events to always log, the when/where/who/what attributes, what to exclude or hash, and tamper detection.
- ICO, [Guide to accountability and governance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/guide-to-accountability-and-governance/): "you must be able to demonstrate your compliance". The audit log is part of that evidence.

**Videos**
- **"Inside your web framework: intro to the ASGI spec, middleware and apps"** by Adrian Garcia Badaracco (a Starlette maintainer), PyCon US 2023. The [PyCon schedule page](https://pycon-archive.python.org/2023/schedule/presentation/5/index.html) is verified, but I couldn't confirm the YouTube URL. Search YouTube for **"Adrian Garcia Badaracco ASGI PyCon US 2023"**. It builds an ASGI app and middleware by hand, the mechanism used here.

## 7. Check your understanding

`READ_METHODS` in `app/audit/middleware.py` decides which methods fail closed. Remove `"GET"` from it (leave `"HEAD"`). **Predict:** which tests fail, and what does the client of `GET /notes/{id}` now receive when the audit write fails?

```bash
uv run pytest tests/test_audit_middleware.py -q
```

**Expected (verified):** exactly one failure, `test_reads_fail_closed_when_the_audit_write_fails`. The response is now **200 with the note**: the data is disclosed with no access row, which is exactly the unlogged read the design exists to prevent. Every other test still passes, because they all have a working audit writer. Restore the line afterwards. Then try the opposite (add `"POST"`) and predict which test fails, and why that's the wrong behaviour for writes.

**Expected (verified):** `test_writes_return_their_real_outcome_when_the_access_row_fails` fails with `assert 500 == 201`. The note *was* created, with its domain events, but the client is told it failed. A retry then gets 409 Conflict, and the client never learns the note id.
