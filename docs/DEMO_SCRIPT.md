# SMARTPBL: 3-minute demo script

A beat-by-beat script for a screen recording, also usable live in an interview. It runs about **3:00**: about 330 spoken words (roughly 2:20 at a calm 140 words a minute), plus pauses for clicks and screen changes.

## Before recording (10 minutes)

**Record against the local stack,** so the LLM extracts a note live. The hosted demo has no LLM (README, "Try the demo").

```bash
docker compose up -d db && uv run alembic upgrade head && uv run python -m scripts.seed_demo
ollama serve                                   # llama3.1:8b pulled
uv run uvicorn app.main:app --port 8000        # API
(cd web && npm run dev)                        # dashboard, http://localhost:5173
(cd mobile && flutter run -d chrome --web-port 8081)   # carer app; phone-size window (390×844)
```

**Checklist:**
- [ ] **Saved rota:** sign in as Hannah, open Schedule and click **Optimise the day** (about 20 s), so Joy has visits.
- [ ] **Queue content:** the review queue already has a few notes. Submit 3–4 from `data/care_notes/dev.jsonl` (see `docs/DEPLOYMENT.md`, Part 5).
- [ ] **Warm-up:** open Workforce once, so the model has trained (about 5 s).
- [ ] **Windows:** dashboard browser at 1440 px wide; carer app in a narrow window on the right, or on a phone mirrored to the screen.
- [ ] **Prepared text:** have this note ready to paste: *"Mr R was up and dressed. Meds taken with water. Said his left knee is more painful going down stairs and he nearly fell on the landing this morning. Ate half his porridge."*
- [ ] **Distractions:** notifications off, browser zoom 100%, bookmarks bar hidden.

## The script

| Time | Screen | Do | Say | What it shows |
|---|---|---|---|---|
| **0:00–0:20** | README top (problem and architecture diagram) | Scroll slowly from "The problem" to the diagram | "Home-care providers face three problems at scale: risks hidden in hundreds of daily notes, rotas that trade driving against continuity of care, and carers leaving. SMARTPBL tackles each with AI, behind a secure API, with a person making every decision." | The problem and the three-part architecture |
| **0:20–0:50** | Carer app: sign in → Today | Sign in as Joy. Point to the progress row and the next-visit card. Tap **Start visit** | "This is the carer app, one Flutter codebase running here as an installable web app. Joy sees today's visits from the optimised rota, the tasks for each one, and a short handover of recent notes, with names removed." | Carer-facing tools; data minimisation |
| **0:50–1:15** | Carer app: Care note | Tick Medication, paste the note, switch on **Raise an urgent concern**, tap **Submit** | "She writes the note as she'd say it. Names and addresses are removed before the local language model reads it. Nothing goes to a cloud AI service. She can also raise an urgent concern, which always reaches a coordinator, whatever the model finds." | Redaction, local inference, a human-review trigger |
| **1:15–1:50** | Dashboard: Review | Sign in as Hannah, open **Review**. The urgent note is at the top. Point to the highlighted evidence and the flags. **Approve** | "On the coordinator side, the note is first in the queue. The model flagged a fall risk, and the exact sentence is highlighted in the note. Every flag must quote the note, or it's rejected. On held-out synthetic notes, the full pipeline let none of 19 high-severity risks through unflagged. I approve, and the decision is stored with a diff." | Grounded NLP, human in the loop, recall-first evaluation |
| **1:50–2:20** | Dashboard: Schedule | Open **Schedule**. Click a carer and a visit to show "why this carer" and "next best". Select the **Continuity** preset to move the point on the trade-off curve | "The rota comes from OR-Tools, solving a vehicle routing problem with time windows, skills and shifts. Every assignment says why, and what the next-best carer would cost. Continuity of care is an explicit price: this curve shows minutes of driving against familiar carers, and the manager picks the point." | Optimisation, explainability, the trade-off as a decision |
| **2:20–2:45** | Dashboard: Workforce | Open **Workforce**. Point to the factors chart and the support actions | "Attrition risk comes from a gradient-boosting model on working conditions the rota itself creates: short-notice changes, long drives. SHAP shows what drives each estimate. It's designed for support only: it suggests rota changes and a check-in, never performance decisions, and every view is audited." | Explainable ML, ethical framing |
| **2:45–3:00** | Dashboard: Audit log, then the README "Results at a glance" | Show the approval at the top of the audit log, then cut to the results table | "Every AI output, human decision and data access lands in an append-only audit log. Everything here is synthetic data, and the limitations are documented. The README links to the evaluation, the data-protection assessment and the model cards." | Accountability; honesty about limits |

## If something goes wrong live

| Problem | Say | Do |
|---|---|---|
| The LLM is slow (over 10 s) | "The model runs locally on my laptop, so it takes a few seconds. In production it would sit on a GPU server inside PBL's network." | Keep talking over the "Sending… checking for risks" state |
| The LLM fails | "If the model is down, the note is still saved with the rules baseline's flags and sent to review. Nothing is lost." | Show the note in the queue marked as a failed extraction |
| The hosted demo is cold | "Both the API and the database scale to zero when idle, so the first request wakes them." | Open the page 2 minutes early next time |
| Joy has no visits | "The carer's day comes from the saved rota, so a coordinator publishes it first." | Click **Optimise the day** as Hannah |

## Cut-down versions

- **60 seconds:** beats 0:00, 1:15 and 1:50, each trimmed to one sentence.
- **Interview opener (90 seconds, no screen):** the problem, the three modules, the human in the loop, "all synthetic, here's what I'd do with real data", then the one result I'm most confident in (scheduling) and the one I'm least confident in (absolute NLP numbers).
