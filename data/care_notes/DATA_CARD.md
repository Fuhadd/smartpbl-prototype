# Data card: Synthetic care notes v1

> **Entirely synthetic.** No real people, clients, carers or PBL Care records were used or consulted. Do not read any metric computed on this data as evidence of real-world performance.

## Summary

| | dev | test |
|---|---|---|
| Notes | 80 | 40 |
| Risk flags | 109 | 56 (exactly 8 per category) |
| Notes with 0 / 1 / 2 / 3 risks | 14 / 33 / 23 / 10 | 6 / 17 / 12 / 5 |
| Severity low / medium / high | 6 / 52 / 51 | 8 / 29 / 19 |
| `follow_up_required` = true | 64 | 30 |
| Words per note (mean, min–max) | 43.0 (21–71) | 40.0 (13–59) |
| Notes with an indirect (hard) phrase | 30 | 19 |
| Notes with a negation distractor | 32 | 16 |
| Notes using a test-only phrase | 0 | 17 |

Generator: `scripts/generate_notes.py`, **seed 42**. Regenerate with `uv run python -m scripts.generate_notes`. A test checks that the committed files match the generator's output.

## Intended use

- **dev**: for building and tuning the keyword baseline (Step 1.4), choosing prompts and few-shot examples (Step 1.5), and setting grounding and routing thresholds (Step 1.6).
- **test**: **only for final evaluation (Step 1.9).** Never look at it while tuning.
- Every note includes PII-like strings (`pii` field) to test redaction (Step 1.3).

Not intended for training models, estimating real risk prevalence, or any clinical decision.

## How it was generated

Each note is built from a phrase library (`scripts/note_templates.py`), so **the labels are correct by construction**.

1. **Risk count** per note comes from a fixed mix (as above), shuffled.
2. **Categories** are assigned in a balanced way: each note takes the least-used categories so far, with random tie-breaks. So every category is equally represented.
3. **One phrase per risk**, from 48 labelled phrases: 32 explicit, 16 *indirect*. Indirect phrases describe the risk without the obvious keyword, e.g. "sat on the bathroom floor… couldn't get herself back up". Each is chosen as indirect with probability 0.35.
4. **Negation distractor** (probability 0.4): a phrase that mentions a risk keyword without the risk being present ("No falls reported since last visit"). It is always for a category with *no* real risk in that note, and is recorded in `negated`.
5. **Medication status**: taken from the medication phrase if there is one. Otherwise 60% `taken` (with a "meds given as per MAR"-style sentence) and 40% `not_mentioned`.
6. **Neutral filler** (1–3 sentences, e.g. "Put the bins out as requested."), then the sentences are shuffled.
7. **Messiness, per note**:
   - abbreviations (p=0.4): `meds`, `w/`, `&`, `approx`, `bfast`, `cl`
   - typos (p=0.5 per note, then 0.3 per sentence): two adjacent inner letters swapped, e.g. `tabelts`
   - all lowercase (p=0.15)
   - no full stops (p=0.2)
8. **Opening sentence**: 60% include synthetic PII. The opening is never given typos, so redaction tests have clean targets.
9. **Gold evidence** is the exact sentence *after* the messiness is applied, so it is always a substring of the note text (enforced by tests).

**Severity rule**: `high` = harm has happened or is likely now (injury, safeguarding, no care delivered); `medium` = needs same-day follow-up; `low` = record only. `follow_up_required` = any flag with severity medium or high.

**Phrase leakage control**: in each (category, explicit/indirect) group, the last phrase (14 in total) is **test-only**. Dev never contains them. Test notes that use them are tagged `unseen_phrase`, so evaluation can report results on seen and unseen phrases separately.

## Synthetic identifiers (chosen to be fictional on purpose)

| Type | Format | Why it can't be real |
|---|---|---|
| Names | `Mrs Sampleton`, `Bravo Fakename` | Placeholder surnames; NATO-alphabet first names |
| Phone | `07700 900000–900999` | Ofcom reserves this mobile range for TV/radio drama; it is never allocated |
| NHS number | `999 xxx xxxx` | The 999 range is reserved for testing and never issued to patients (no checksum is applied here, so these may also be invalid) |
| Postcode | `ZZ<1-99> <digit><2 letters>` | `ZZ` is not a UK postcode area |
| Address | `<n> Example Street` etc. | Placeholder street names |

## Known biases and limitations

- **Narrow vocabulary.** 48 risk phrases, 9 fillers and 14 negations. Real notes are far more varied. A model that does well here may not generalise.
- **Favours a keyword baseline.** Explicit phrases contain the obvious keywords. Indirect phrases and held-out phrases offset this only partly.
- **One sentence = one risk.** Real notes spread risks across sentences and mix risks inside a single sentence.
- **Negation is simple.** It is always a separate sentence with "no"/"denies". There are no scoped negations ("no injury *but* bruised hip") and no hedging ("possibly", "?fall").
- **Low severity is under-represented** (6 of 109 dev flags). Severity metrics for `low` will be noisy.
- **Female clients only.** The phrases use she/her, and titles are Mrs/Ms/Miss. Most domiciliary care clients are older women, but this still leaves male clients and non-gendered phrasing untested.
- **British English only.** No transcribed speech, no carers writing in English as a second language, no non-English text, though all of these appear in real notes.
- **Small and contradiction-free by design.** There are no conflicting statements, which real notes sometimes contain ("ate well" but "breakfast untouched").
- **Prevalence is artificial.** 83% of notes have at least one risk, far above any realistic rate. Precision on real data would be lower for the same model.
- **The labels reflect one author's judgement.** No inter-annotator agreement was measured.

## Fields (`LabelledNote`, see `app/nlp/dataset.py`)

`note` (`CareNote`) · `gold.risk_flags[]` (`category`, `severity`, `evidence`) · `gold.medication_status` · `gold.follow_up_required` · `negated[]` · `pii[]` · `tags[]` ∈ {`no_risk`, `single`, `multi`, `hard`, `negation`, `noisy`, `lowercase`, `pii`, `unseen_phrase`}
