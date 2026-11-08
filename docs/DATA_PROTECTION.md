# Data protection note (DPIA-style)

**Status:** a prototype-stage assessment, written to show how SMARTPBL would be assessed before it processed real data. **The prototype processes synthetic data only.** This note is not legal advice. Before any real data is used, PBL Care's DPO, Caldicott Guardian and staff representatives must complete and sign off a full DPIA.

## 1. Why a DPIA is needed

The ICO says a DPIA is required for processing that is likely to be high risk. SMARTPBL meets several of its criteria at once:
- **Special category data at scale:** health and social care information in care notes, processed at scale (Article 35(3)).
- **Innovative technology:** AI applied to that data.
- **Profiling of employees:** attrition risk scoring. Workers are vulnerable data subjects because of the power imbalance with their employer.

## 2. What is processed

| Data | Whose | Where it lives | Category |
|---|---|---|---|
| Care-note text | Clients (plus any names written in the note) | Raw text in Postgres; **redacted** text for the LLM, the API and the UI | Special category (health) |
| Risk flags, review decisions | Clients; reviewers | Postgres, with reviewer diffs | Special category (derived) |
| Visits, skills, time windows, preferred carers | Clients; carers | Scheduling input; runs store **assignments only, plus a keyed hash of the input**, no locations | Personal; health-related (care needs) |
| Client and carer locations | Clients; carers | Scheduling input only; not persisted with runs | Personal |
| Working-condition features (drive time, gaps, rota changes, tenure, contract) | Carers | Model training data; scores are computed on read and not stored | Personal; **profiling** |
| Age band | Carers | Fairness audit only; **never a model input, never returned** | Personal (protected characteristic) |
| Accounts, tokens, audit events | Staff | Postgres: Argon2id password hashes; refresh-token ids, not tokens; audit rows with **HMAC input hashes**, not content | Personal |

## 3. Lawful basis

Each basis below is **to be confirmed with PBL's DPO**. These are the expected positions.

- **Care notes and scheduling.**
  - **Article 6:** the basis PBL already relies on to deliver care, likely contract with the client, or public task where care is local-authority commissioned.
  - **Article 9:** condition **9(2)(h) health or social care**, with **DPA 2018 Schedule 1 condition 2**. The data must be processed by, or under the responsibility of, someone who owes a duty of confidentiality, and the processing must be necessary and proportionate. Using AI to *prioritise* review sits within providing care. Using the notes to *train* a model is a further purpose, which needs its own assessment.
- **Attrition scoring.**
  - **Article 6(1)(f) legitimate interests,** tested by the ICO's three parts:
    - **Purpose:** keeping staff and continuity of care.
    - **Necessity:** a less intrusive option (team-level reporting only) must be shown to be insufficient.
    - **Balancing:** workers would reasonably expect support offers, not adverse use.
  - **No special category data** is used.
  - **No solely automated decisions** (Article 22): every score is a prompt for a human-led, supportive conversation.
  - **Staff must be told** in the workforce privacy notice and consulted before launch.

## 4. Controls in the design

| Principle | How SMARTPBL implements it | Evidence |
|---|---|---|
| **Data minimisation** | Presidio and UK recognisers mask names, addresses, postcodes and phone numbers **before** the LLM. The API and UI show only redacted text. The audit log stores HMAC hashes, not inputs. Runs don't store locations. The label and age are never served. Carer handovers are limited to the last 3 notes for today's clients. | Notes 03, 07, 15, 19, 29 |
| **Local inference** | The LLM runs on PBL-controlled hardware (Ollama). No care data goes to a third-party AI API. | ADR-001, ADR-008 |
| **Accuracy and hallucination control** | Every flag must quote the note (grounding). High-severity, safeguarding, low-confidence and fuzzy flags go to a human. A rules baseline catches what the LLM misses. Measured on held-out data. | ADR-009, ADR-013 |
| **Human oversight** | Coordinators approve, edit or reject each flag (diff stored). High-severity flags can be escalated to a manager. Carers can force review with an urgent concern. Attrition outputs are supportive prompts only. | ADR-011, ADR-031, ADR-035, attrition model card |
| **Access control** | JWT roles with least privilege. Carers see only their own rota (object-level checks). Managers oversee but don't decide flags. Hidden pages are still refused server-side. | ADR-025, ADR-035, `SECURITY.md` |
| **Accountability** | An append-only audit of every AI output, human decision, data read (including who saw which carer's risk and which client notes) and denied access, with request correlation and CSV export. | ADR-010, ADR-026, ADR-032 |
| **Security** | OWASP API Top 10 review, rate limits, secure defaults, TLS. Hosting is UK-region (London) for both the database and the API. | ADR-027, `SECURITY.md` |

## 5. Retention (proposed; to be agreed with PBL)

| Data | Proposed retention | Reason |
|---|---|---|
| Care notes and their flags and decisions | Per PBL's schedule under the **Records Management Code of Practice for Health and Social Care** (local adult social care schedules commonly use 8 years after care ends) | They are part of the care record |
| Audit events | The same period as the record they describe; hashes rather than content, so they can be kept without re-exposing the text | Accountability for decisions about care |
| Schedule runs (assignments, reasons) | 2 years, then aggregate | Operational review; no locations stored |
| Workforce scores | Not stored; recomputed on read. Training data is refreshed on retraining, and leavers' data is removed after the employment-records period | Minimise profiling records |
| Refresh-token rows | Deleted after expiry (7 days) | Security only |

## 6. Risks and mitigations

| Risk | Likelihood × impact (before) | Mitigation | Residual |
|---|---|---|---|
| Identifiers survive redaction and reach the LLM or the UI | Medium × High | UK recognisers, tests per format, local LLM only, redacted text everywhere downstream | Low; monitor with sampled audits |
| Missed risk (false negative) delays care | Medium × High | Recall-first evaluation, rules safety net, carer urgent switch, coordinators still read notes | Medium; human processes stay primary |
| Hallucinated or wrong flag | Medium × Medium | Grounding rejects quotes that aren't in the note; human review for uncertain or high flags | Low |
| Attrition score used punitively | Medium × High | Model card prohibitions, supportive-only actions, use notice on every screen and response, audited views, manager-only access | Medium; needs policy and training |
| Proxy discrimination (e.g. age via tenure) | Medium × High | Age excluded from inputs, an age audit run (shows disparity), controls on use, not on the score | Medium; audit every lawfully measurable characteristic with real data |
| A carer or coordinator reads data outside their role | Low × High | Least-privilege roles, object-level checks, 404 for others' objects, audit of every read | Low |
| Audit log altered by a privileged insider | Low × Medium | Append-only trigger against the application | Medium; add separate DB roles and a hash chain or WORM storage |
| Demo credentials or synthetic data mistaken for real | Low × Low | Seeding refused outside `local`/`demo`; "synthetic" badge on every screen | Low |

## 7. Before real data: actions and sign-off

1. **Full DPIA,** signed by the DPO and Caldicott Guardian, with this note as its starting point.
2. **Agreements:** a data-sharing agreement with BCU (KTP) covering access to pseudonymised extracts for model work.
3. **Privacy notices:** updated for clients and staff. **Consult staff and unions** on the attrition module before any pilot.
4. **Fresh evaluation** on real, consented, pseudonymised notes, with clinician-agreed labels, and a fairness audit on real workforce data.
5. **Security for production:** encryption at rest for raw note text, separate DB roles, SSO, and patch-scoped access.
