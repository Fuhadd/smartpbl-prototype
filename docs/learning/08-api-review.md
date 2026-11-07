# 08 — API and human review

## 1. What was built

| File | Purpose |
|---|---|
| `app/api/notes.py` | `POST /notes` (redact → extract → ground → route → persist; 201, or 409 on a duplicate `note_id`) and `GET /notes/{id}` |
| `app/api/review.py` | `GET /review/queue` (notes needing review, highest pending severity first) and `POST /review/{flag_id}` (approve / edit / reject) |
| `app/api/audit.py` | `GET /audit/{note_id}`: the note's audit trail in insertion order |
| `app/api/schemas.py` | API response models, separate from the ORM. `raw_text` is deliberately absent |
| `app/api/deps.py` | Dependencies: LLM client, prompt, and the `X-Reviewer` header (a prototype stand-in for auth) |
| `app/nlp/review.py` | Review service: row lock, edit validation and re-grounding, before/after diff, decision row, audit event |
| `app/nlp/models.py` | Adds the `ReviewAction` enum and the `review_decisions` table |
| `migrations/versions/0002_review_decisions.py` | Creates `review_decisions`, with a CHECK constraint on `action` and a foreign key to `risk_flags` |
| `tests/test_api.py` | 21 integration tests: real routers, real test Postgres, LLM replaced by `FakeClient` through `dependency_overrides` |

Verified live: `uvicorn` with the real `llama3.1:8b` on the dev database. Ingest took 18 s from cold. The test then ran queue → edit → repeated decision (409) → audit trail (6 events, the last by `user:coord.alpha`).

## 2. Why this way

- **Routers are thin; the logic lives in a service.** `review_flag()` knows nothing about HTTP. It raises domain errors, and the router turns them into status codes (404, 409, 422). The same function can serve a CLI, a job queue or the Flutter app's backend without change, and it can be tested without HTTP.
- **Each review is one transaction with four writes:** lock the flag, update it, insert a `review_decisions` row, append the audit event. Either the decision exists everywhere or nowhere. An audit row saying "approved" for a decision that was rolled back would make the audit log lie.
- **The flag row is locked with `SELECT … FOR UPDATE`.** Two coordinators can open the same high-severity flag. Without the lock, both read "pending", both write, and the second silently overwrites the first (a *lost update*). With it, the second waits, then sees "approved" and gets 409.
- **Decisions are final, and decided flags return 409.** Silently re-deciding a safeguarding flag is the dangerous failure. A correction workflow, where a manager re-opens a flag with a reason, is backlog.
- **Auto-accepted flags can still be rejected.** A coordinator who spots a false positive must be able to say so. These corrections are exactly the labels a future evaluation needs.
- **Edited evidence must still be a quote from the note.** It is re-grounded against the redacted text, and the stored evidence is the matched span of the note, not the reviewer's typed text. The invariant from 1.6, "every stored evidence span is in the note", therefore survives human edits. It also stops a reviewer typing a client's name into evidence: the name isn't in the redacted text, so the edit is ungrounded and rejected (422).
- **Free-text comments go in `review_decisions` but never into the audit log.** Comments are where people write names ("rang Mrs X's daughter"). The audit log is permanent and must not hold personal data, so it records only `has_comment: true`. `review_decisions` is ordinary operational data and falls under the retention policy.
- **Two stores for decisions.** `review_decisions` is typed, has a foreign key and is easy to query, for example "edit rate per category". The audit event is the tamper-resistant evidence and survives deletion of the note.
- **The API returns redacted text only.** `NoteOut` is a separate Pydantic model, so a column reaches the API only by a deliberate edit to `schemas.py`, not because someone added it to the ORM. This guards against OWASP API3:2023 (excessive data exposure). Raw text will come back in Tier 4, behind a role check and an audited read.
- **`POST /notes` checks for duplicates before calling the LLM.** It fails fast, without spending 6 s of compute. It then calls `session.rollback()` so it doesn't hold a database connection during the LLM call: the SELECT has already opened a transaction (SQLAlchemy autobegin). A unique constraint, caught as `IntegrityError` → 409, still guards against a concurrent duplicate.
- **The reviewer is identified by the `X-Reviewer` header.** This is a declared shortcut: anyone can claim any name. It exists so the audit actor field is populated now. Step 4.1 replaces it with the authenticated JWT subject.

## 3. Alternatives considered

| Option | Pros | Cons | When I'd choose it |
|---|---|---|---|
| **Pessimistic lock (`FOR UPDATE`), chosen** | Simple; correct; the losing reviewer gets a clear 409 | Holds a row lock for the transaction (milliseconds here); risk of deadlock if several rows are locked in different orders | Short transactions, low contention, correctness critical |
| Optimistic concurrency (version column / ETag + `If-Match`) | No locks; also detects "edited while I was reading" across the UI round trip | More moving parts (version column, 412 handling in the client) | When reviewers spend minutes on a screen. The Flutter app (5.2) may want this |
| Diff only in the audit log (no `review_decisions` table) | One source of truth; no extra migration | Querying JSONB in a generic log for metrics is awkward; comments would have to go there too (PII) | A smaller system with no analytics on reviews |
| Event-sourced flags (state rebuilt from decisions) | Perfect history by construction | Replay, projections and much more complexity for a prototype | Large, audit-heavy domains with many state transitions |
| Async ingest (202 + job queue) | Fast API responses; retries; absorbs LLM spikes | Needs a broker and workers; the client must poll | Production volumes, or when the LLM is remote or slow |

## 4. How it works

**Review transaction:**

```mermaid
sequenceDiagram
    participant C as Coordinator A
    participant D as Coordinator B
    participant API
    participant PG as Postgres
    C->>API: POST /review/{flag} approve
    API->>PG: SELECT ... FROM risk_flags WHERE id=… FOR UPDATE
    D->>API: POST /review/{flag} reject
    API->>PG: SELECT ... FOR UPDATE (blocks)
    API->>PG: UPDATE risk_flags; INSERT review_decisions; INSERT audit_events
    API->>PG: COMMIT (lock released)
    API-->>C: 200 approved
    PG-->>API: B's SELECT returns status=approved
    API-->>D: 409 already reviewed (approved)
```

**The diff** compares two snapshots of the reviewable fields and keeps only those that changed. In the live run the reviewer lowered a medication flag from high to medium:

```json
{"severity": {"before": "high", "after": "medium"},
 "review_status": {"before": "pending", "after": "edited"}}
```

Editing evidence also changes the span and grounding fields. The test edits `"found on the floor"`, which matches by normalisation. The stored evidence becomes `"Found on the floor"`, the note's own capitalisation, and the diff includes `span_end` and `grounding_status: exact → normalised`.

**Queue priority:**
- Notes with `review_required = true` come first by their highest *pending* severity, then oldest first.
- A failed LLM extraction counts as medium: the risk is unknown, and the baseline may have seen only part of it.
- Auto-accepted flags are hidden from the queue but remain on the note.
- When the last pending flag is decided, `review_required` becomes false and the note leaves the queue.

**Testing with dependency overrides:** `app.dependency_overrides[get_session] = lambda: db_session` makes every request use the test's session. That session sits inside an outer transaction which is always rolled back (see 07), so even `session.commit()` inside a route leaves nothing behind. `get_llm_client` is overridden with `FakeClient`, so no test needs Ollama.

**Tests were checked by deliberately breaking the code** (each change reverted afterwards):
- Removing `with_for_update=True` failed the lock test.
- Removing the rollback after an invalid edit failed the "no-op edit" case. The service changes the flag in memory before it detects that nothing really changed, so the router's rollback is load-bearing.
- Adding `raw_text` to `NoteOut` failed the PII test.

## 5. Interview questions and answers

**Q1. Two coordinators review the same flag at once. What happens?**
The service loads the flag with `SELECT … FOR UPDATE`, so the second transaction blocks until the first commits. It then reads the new status, finds the flag already decided and gets a 409 naming the existing decision. Without the lock both would read "pending" and the later write would silently win. That is a lost update, which for a safeguarding flag means a decision vanishes from the current state. A test asserts the lock is in the emitted SQL, and fails if it's removed.

**Q2. Why can't a reviewer type any evidence they like?**
Evidence is the contract that makes a flag checkable: anyone can find it in the note. Edited evidence is re-grounded against the redacted note, and the stored value is the note's own matched span, so the "evidence is in the note" invariant holds for human edits as well as model output. As a side effect, a reviewer can't introduce a client's name into a flag, because names aren't in the redacted text. Free-form reasoning belongs in the comment field.

**Q3. Why are comments stored but kept out of the audit log?**
Comments are free text written by busy staff and will contain names and health details. The audit log is append-only and outlives the note, so anything personal written there can never be erased, which conflicts with storage limitation and erasure rights. The log records that a comment exists. The comment lives in `review_decisions`, which the retention policy can delete.

**Q4. Trade-off: why a synchronous `POST /notes` when it takes 6–18 seconds?**
For a prototype with one coordinator it is the simplest correct design: the response contains the flags, and errors surface immediately. The costs are a worker thread tied up per request, timeouts behind proxies, and no retry if the LLM fails. The pipeline already degrades to baseline flags rather than losing the note. At PBL scale I'd accept with 202, put a job on a queue, have workers run the pipeline with retries, and let the app poll or receive a push. The persistence and audit code wouldn't change, because `process_note` is already independent of HTTP.

**Q5. Why separate API schemas from the ORM models?**
The API is a contract and a privacy boundary. If responses were serialised straight from ORM rows, adding a column such as an encrypted raw-text field or a carer's phone number would publish it automatically. That is OWASP API3, excessive data exposure. With explicit `NoteOut`/`FlagOut` models, exposure is a reviewed change to one file. A test fails if `raw_text` or any synthetic PII appears in a response.

**Q6. Is `X-Reviewer` authentication?**
No, and the code says so. It is an identity claim with a strict pattern, used so the audit actor field is populated from day one. Anyone can send any name, so it gives no access control. In Step 4.1 the dependency is replaced by one that returns the JWT subject and checks the coordinator role. Routes and tests barely change, because the reviewer is already injected as a dependency.

**Q7. With real PBL data, what changes?**
- Authenticated identities and role checks on every route, and auditing of reads as well as writes.
- Raw text access for authorised roles only, logged.
- Async ingest with idempotency keys, so a carer's app can safely retry.
- Optimistic concurrency (ETags) for long-lived review screens.
- A priority column with SQL paging instead of sorting in Python.
- Reviewer decisions become the most valuable dataset PBL has: real labels for measuring and improving extraction. The edit-rate per category would be monitored as a drift signal.

**Q8. Why can auto-accepted flags be rejected but decided flags can't be changed?**
They differ in who decided. An auto-accepted flag was decided by policy with no human involved, so a human overriding it is the system working as intended. A human decision has accountability attached, and silently replacing it would undermine both the audit trail and the person's sign-off. Re-opening a decision should be an explicit, reasoned, separately audited action, which is in the backlog.

## 6. Learn more

**Official documentation**
- FastAPI, [Testing Dependencies with Overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/): the `dependency_overrides` mechanism used for the session and the fake LLM.
- FastAPI, [Response Model – Return Type](https://fastapi.tiangolo.com/tutorial/response-model/): how return types filter output. This is the mechanism behind withholding `raw_text`.
- PostgreSQL 16, [Explicit Locking](https://www.postgresql.org/docs/16/explicit-locking.html): row-level lock modes (`FOR UPDATE`, `FOR NO KEY UPDATE`, …), their conflicts and deadlocks.
- OWASP, [API3:2023 Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization): formerly "Excessive Data Exposure"; why responses should list their fields explicitly.

**Video**
- *Transactions: myths, surprises and opportunities*, Martin Kleppmann (Strange Loop 2015), https://www.youtube.com/watch?v=5ZjhNTM8XU8. The title is verified; I couldn't confirm the uploading channel's name from the page. It's the clearest talk on what isolation levels do and don't protect against, including lost updates. Watch it to understand why `FOR UPDATE` is needed even inside a transaction.

## 7. Check your understanding

1. In `app/nlp/review.py`, change `REVIEWABLE` to `frozenset({ReviewStatus.PENDING})`. Predict which test fails and with what status code, then run `uv run pytest tests/test_api.py`. Revert afterwards.
   **Expected:** `test_reviewer_can_reject_an_auto_accepted_flag` fails with `assert 409 == 200`. Coordinators could no longer correct a false positive that was auto-accepted.
2. Predict what the API does with an edit to the falls flag in `FALL_TEXT` whose evidence is (a) `"Mrs Sampleton found on the floor by the bed"` and (b) `"found on the flor by the bed"` (typo). Check with `ground(evidence, redact(FALL_TEXT).text)`.
   **Expected:**
   - (a) **422**: ungrounded, score 74.4. The name isn't in the redacted text, so it can't enter the flag.
   - (b) **accepted** as `fuzzy`, score 96.4. The stored evidence is the note's own text, `"Found on the floor by the bed."`.
