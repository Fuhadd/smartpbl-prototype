# 25 — Care-note review screen (Step 5.2a)

## 1. What was built

**Backend**

| File | Purpose |
|---|---|
| `app/nlp/review.py` | `decide_note()`: decides **every pending flag of one note in one transaction**, through the existing `review_flag` (row lock, diff, one audit event per flag). Decisions must cover exactly the pending flags. Optional escalation, allowed only when a kept flag is high severity. A note with no flags (LLM failed, rules found nothing) can be acknowledged |
| `app/api/review.py`, `schemas.py` | `POST /review/notes/{note_id}` (`review.decide`; 404, 409, 422). `QueueItem` gains `carer_ref`; `NoteOut` gains `escalated_at` and `escalated_by` |
| `app/nlp/models.py`, `app/audit/models.py`, migration `0008` | `care_notes.escalated_at` / `escalated_by`; new audit event `review_escalated` (CHECK edited by hand; downgrade refuses if such events exist) |
| `tests/test_note_review.py` (11), `test_auth_api.py` (+1 matrix row) | All-or-nothing behaviour, mixed decisions, escalation recorded and refused, coverage of exactly the pending flags, rollback on one invalid edit, double decision, 404, carer on queue items |

**Frontend (`web/src/review/`, `pages/ReviewPage.tsx`)**, rebuilt from `docs/design/screens/Review.dc.html`:

| Piece | Design element |
|---|---|
| `ReviewHeader` | White bar: "Review queue / CL-0142 · Visit note", the risk chip ("High risk"), the demo badge, Previous / Next note |
| `ReviewQueue` | Left panel: count, All / High / Medium filter, priority dot, "CL-0142 · Falls", "CR-0007 · 08:47 · 1 flag" ("Yesterday", "Thu", then a date) |
| `OriginalNote` | Redacted note with **evidence spans highlighted in category colours**, `[NAME]` / `[PHONE]` chips, "2 identifiers redacted" |
| `ExtractionPanel` | "AI EXTRACTION" with sparkle and "llama3.1:8b · prompt v2 · 23.4 s"; one card per flag (swatch, label, severity as **text and colour**, confidence, grounding, quoted evidence); medication and follow-up tiles; Edit / Reject / Approve extraction |
| `DecisionSupport` | Why this needs review (built from `review_reasons`), safety checks (grounded n/n, schema, identifier types, data left device), approval routing (Done / Current / Required / Escalated), **Escalate to care manager** (only while a kept flag is high) and **Approve and log decision** |
| `Protocol` | "PBL FALLS PROTOCOL" with the design's placeholder text (other categories: no card until PBL supplies text) |
| `decisions.ts`, `queue.ts`, `noteText.ts`, `format.ts` | Pure logic, unit-tested: staged drafts → decision list; filters; note segmentation; copy |
| States | Loading skeleton, "All caught up" empty state, error state with request reference, a conflict message on 409 |

Tests: Python **351**, web **38** (unit tests plus 10 screen tests against a fake API). In headless Chrome, the screen beside `Review.dc.html`: same layout, copy and colours. Escalating **through the real browser and API** wrote one `review_decision`, one `review_escalated` (`[{"category": "falls", "severity": "high"}]`) and a correlated `api_request`, set `escalated_by`, removed the note from the queue and moved to the next note.

## 2. Why this way

**One request per note, all or nothing.** The design decides the *extraction*: Approve, Reject, Escalate. The API decided one *flag* at a time. Approving three flags with three calls risks a partial state: two approved, the third fails on a network blip, and the note sits half-decided with the audit log telling a confusing story. `POST /review/notes/{id}` applies every decision in one database transaction. It locks the note row, and each flag row through `review_flag`, and requires the decisions to cover **exactly** the pending flags. One bad edit (evidence that isn't a quote from the note) rolls back the whole set; a test proves the other flags stay pending. Per-flag history is unchanged: every flag still gets its own `review_decisions` row with a diff, and its own audit event.

**Escalation as recorded state, not a flag in a log message.** The designs show "Escalate to care manager", an approval-routing row "Care manager sign-off · Required", and an audit row "Escalated to care manager (falls, high)". I store `escalated_at` / `escalated_by` on the note (operational state the UI can query) and append a `review_escalated` audit event listing the high-severity flags (the history). The server enforces DESIGN.md's rule that escalation is for high severity: escalating with no kept high flag is a 409, and the frontend only shows the button while one is kept, including after an edit downgrades it. The care manager's own sign-off screen isn't in the designs, so it's in the backlog.

**Evidence highlighting from offsets, not string search.** The API's grounding step (Step 1.6) stores each flag's character offsets into the redacted note. The screen uses those offsets directly, so the highlight is exactly the text grounding verified. Searching for the quote again in the browser could highlight a different occurrence, or nothing after an edit. Overlapping or out-of-range spans are dropped rather than garbling the note (tested).

**A deterministic title instead of the model's summary.** My first build titled the page with the LLM's summary. Against the real model that was three lines long and contained a raw `<PERSON>` token. The design's "Fall reported during morning visit" reads as a headline built from the top flag and the visit time, so that's what the code builds; for this note it reproduces the design's title exactly. It also keeps AI text inside the AI panel, which DESIGN.md asks for.

**Severity is never colour alone** (WCAG 2.2 SC 1.4.1, Level A). Every severity appears as a word ("High", "Medium"), and queue dots carry screen-reader text ("high priority").

**Server-derived explanations.** "Why this needs review" is generated from the flags' `review_reasons`, the codes the routing step (Step 1.6) wrote. The screen therefore explains the real routing decision, not a guess. The confidence threshold (0.70) mirrors `app/nlp/route.py` as a constant; exposing it through the API is in the backlog.

**Design gaps filled (for review):**
- colours for the four categories DESIGN.md doesn't cover (medication, skin integrity, safeguarding, missed or late visit);
- edit-mode controls (category and severity selects, evidence textarea, "Reject flag");
- the read-only view for managers and for decided notes;
- the 409 conflict message;
- the failed-extraction banner.

## 3. Alternatives considered

| Option | Pros | Cons | When I'd choose it |
|---|---|---|---|
| **Note-level atomic endpoint (chosen)** | No half-decided notes; one audit story; one request | A new endpoint; must validate coverage | Any UI that decides a group of items as one act |
| N per-flag calls from the browser | No backend change | Partial failure leaves inconsistent state; N round trips | Truly independent items |
| Batch endpoint with partial success (207-style results) | Some progress on errors | Harder UI and audit semantics ("which failed?") | Bulk tools where partial progress is acceptable (imports) |
| Escalation only as an audit event | No schema change | The UI must query the audit log to know state; slower and couples UI to the log | A one-off notification with no follow-up workflow |

## 4. How it works

```mermaid
sequenceDiagram
  participant UI as Review screen
  participant API as POST /review/notes/{id}
  participant DB as Postgres
  UI->>UI: drafts per pending flag (approve / edit fields / reject)
  UI->>API: {decisions:[...all pending...], escalate}
  API->>DB: SELECT note FOR UPDATE
  API->>API: decisions == pending flags? else 409
  loop each flag
    API->>DB: SELECT flag FOR UPDATE; apply; INSERT review_decisions; INSERT audit review_decision
  end
  alt escalate
    API->>API: any kept HIGH flag? else 409 (rollback all)
    API->>DB: note.escalated_*; INSERT audit review_escalated
  end
  API->>DB: COMMIT (or ROLLBACK on any error)
  API-->>UI: note (review_required false), decision ids
  UI->>UI: invalidate queue, go to next note
```

**Draft → decision, worked example.** Pending flags A (falls, high) and B (nutrition, medium). The reviewer clicks Edit, sets A's severity to medium and marks B "Reject flag", then clicks Approve extraction:

    A: severity changed            -> {flag_id: A, action: "edit", edit: {severity: "medium"}}
    B: reject                      -> {flag_id: B, action: "reject"}
    (unchanged flags               -> {action: "approve"})

Only changed fields are sent. Evidence is trimmed, so whitespace-only changes count as unchanged. The server re-grounds edited evidence, and any edit that isn't a quote rejects the whole set with 422.

**Highlighting.** Offsets are into `redacted_text`, which includes placeholders like `<PERSON>`. So highlights are placed first, on the raw string, and placeholders are swapped for chips inside each piece afterwards. Doing it the other way round would shift every offset.

## 5. Interview questions and answers

**Q1. Walk me through the review screen.**
It's a three-column page rebuilt from the design:
- **Left:** the queue, filtered by severity.
- **Centre:** the redacted note with each flag's evidence highlighted in its category colour, and next to it the AI extraction with model, prompt version and latency. Each flag shows severity as text and colour, plus confidence and grounding.
- **Right:** why it was routed (generated from the server's routing reasons), safety checks, the approval route, and the decision buttons.

The reviewer can edit or reject individual flags, then approve, reject or escalate the whole note in one atomic request, and moves straight to the next note.

**Q2. Why add a note-level endpoint when per-flag review already existed?**
Because the user's act is "decide this note", and the system should never record half an act. With per-flag calls, a failure on the third flag leaves two decided and one pending, and an audit log that doesn't match what the reviewer meant. The new endpoint runs every decision in one transaction, requires them to cover exactly the pending flags, and rolls everything back if any edit is invalid, which I test explicitly. Per-flag history is preserved: each flag still gets its own diff and audit event.

**Q3. How do you make sure the highlight shows the evidence the model actually cited?**
The highlight uses the character offsets that the grounding step stored when it verified the quote against the note, not a fresh search in the browser. So what's highlighted is exactly the text that passed grounding. Offsets refer to the redacted string, so I place highlights first and render redaction placeholders inside them afterwards. Overlapping or invalid spans are dropped rather than corrupting the displayed note.

**Q4. Trade-off: why is escalation only allowed for high severity, and who enforces it?**
DESIGN.md says escalation appears for high severity, so a care manager's attention is reserved for what needs it. Too many escalations and they stop being read. The UI only shows the button while a kept flag is high, which updates live if the reviewer downgrades the flag. The server enforces it independently: an escalation with no kept high flag is a 409, and nothing in the request is applied. The UI is a convenience; the API is the rule.

**Q5. Why didn't you use the LLM's summary as the page title?**
I did at first, and testing against the real model showed why not: the summary was three lines long and contained a raw `<PERSON>` placeholder. The title now comes from the top flag and the visit time ("Fall reported during morning visit"), which matches the design and is deterministic. It also respects the design rule that AI-generated text sits inside the clearly marked AI panel, so a coordinator never mistakes model output for a fact in the page chrome.

**Q6. With real PBL data, what would you change?**
- **Sign-off:** a care-manager sign-off queue for escalated notes, with its own audit trail and time-to-sign-off monitoring.
- **Protocols:** PBL's actual protocols per category, which is a knowledge-transfer task with the registered manager.
- **Names:** display names for clients and carers resolved server-side under access control, instead of pseudonymous refs.
- **Policy:** exposing routing settings (confidence threshold, safeguarding rule) through the API, so the screen can't drift from the policy.
- **Research:** user testing with coordinators on the edit flow, because what reviewers change is the most valuable training signal we collect.

## 6. Learn more

**Official documentation**
- W3C, [Understanding SC 1.4.1: Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) (WCAG 2.2, Level A): why severity is shown as text as well as colour.
- TanStack Query, [Invalidations from Mutations](https://tanstack.com/query/latest/docs/framework/react/guides/invalidations-from-mutations): `onSuccess` and `invalidateQueries`, the pattern used after a decision.
- shadcn/ui, [Vite installation](https://ui.shadcn.com/docs/installation/vite) and Tailwind, [Dark mode](https://tailwindcss.com/docs/dark-mode) (both from note 24) still apply to the components used here.

**Videos**
- I couldn't verify a suitable video for this step. Search YouTube for **"human in the loop machine learning UX" PyData** or **"designing AI review interfaces" talk**.

## 7. Check your understanding

In `web/src/review/DecisionSupport.tsx`, the Escalate button renders only when `hasHigh` is true. In `ReviewPage.tsx`, `hasHigh` is computed from *kept* pending flags using the *drafted* severity. Change it to use the flag's original severity (`f.severity` instead of `drafts[f.id]?.severity ?? f.severity`). **Predict:** which screen test fails, and what bad request could a reviewer then send?

```bash
cd web && npx vitest run src/pages/ReviewPage.test.tsx
```

**Expected (verified):** `offers escalation only while a high-severity flag is kept` fails. After downgrading the falls flag to medium, the Escalate button stays visible.

A reviewer could then send `escalate: true` together with an edit that removes the only high flag. The server answers 409 ("only a note with a kept high-severity flag can be escalated") and applies nothing. That's the defence in depth: the UI hides the action, and the API refuses it anyway. Restore the line afterwards.
