# Model card: carer attrition risk (SMARTPBL Tier 3)

Structure follows Mitchell et al., *Model Cards for Model Reporting* (2019). **This model is trained on synthetic data and must not be used on real carers.** It shows how the real model would be built, evaluated, explained and governed.

## Model details

| | |
|---|---|
| Model | `HistGradientBoostingClassifier` (scikit-learn 1.9.1): 150 trees, max depth 2, learning rate 0.03, min 20 samples per leaf. Chosen by a 3-fold grid search on log loss |
| Challenger | Logistic regression on standardised features (C chosen in the same way) |
| Output | Probability of leaving within 12 months of a snapshot date, plus per-feature SHAP contributions (log-odds) |
| Inputs | 12 working-condition and employment features (`app/workforce/data.py::FEATURES`). **No protected characteristics** |
| Code | `app/workforce/models.py`, `app/workforce/explain.py`; experiments in `scripts/train_attrition.py` and `scripts/explain_attrition.py` |
| Seed, version | Seed 42; `shap` 0.54.1, TreeExplainer, `tree_path_dependent` (ADR-022) |
| Owner | SMARTPBL prototype (KTP application portfolio), 2026-11 |

## Intended use

- **Primary use:** help a care coordinator or registered manager decide **where to offer support** with working conditions. Examples: give more rota notice, tighten unpaid gaps, build a regular round of familiar clients, check in on new starters, discuss guaranteed hours.
- **Primary users:** coordinators and managers trained to read risk as a prompt for a supportive conversation, with the carer's own view taking precedence.
- **The unit of action is the rota, not the person.** Explanations name the levers the provider controls. A good outcome is a better rota, not a "managed" carer.

## Out-of-scope uses (prohibited)

- **Any decision that disadvantages a carer:** dismissal, discipline, withholding shifts, pay, training or promotion. Flagged carers must never be offered fewer hours "because they're leaving anyway".
- **Recruitment or screening** of applicants.
- **Solely automated decisions** about individuals (UK GDPR Article 22; the ICO notes its guidance is under review following the Data (Use and Access) Act 2025). A human reviews every flag, and acting on a flag means offering something.
- **Use on real carers** without retraining on PBL data, a DPIA, worker consultation, and a fresh evaluation including the fairness audit.

## Factors

- **Age band** is audited because it correlates with tenure and contract type (Equality Act 2010, section 19: indirect discrimination).
- **Not audited, because the synthetic data doesn't contain them:** sex, ethnicity, disability, and migrant status. For international recruits, visa sponsorship changes both the reasons for staying and the consequences of being flagged. With real data, each needs an audit where it can lawfully be measured.

## Metrics

| Metric | Why |
|---|---|
| ROC-AUC | Ranking quality, independent of the base rate |
| PR-AUC (average precision) | Ranking among likely leavers; chance level = base rate (30%) |
| Precision in top 10% / 20% | What a fixed number of support conversations buys |
| Brier score, reliability diagram | Whether "30% risk" means 30% |
| Selection rate by age band, ratio to the most-flagged band | Indirect-discrimination screen (the four-fifths heuristic, not a legal test) |

## Training and evaluation data

- **Data:** 1,000 synthetic carers (`data/workforce/DATA_CARD.md`). Working conditions come from Tier 2 solver output; employment features come from stated assumptions.
- **Label:** produced by a documented ground-truth model with an unobserved factor.
- **Split:** 800 train / 200 test, stratified. The test split is unusually easy (97th percentile of possible splits).
- **Main estimate:** 5×5 nested repeated stratified CV on the training set.

## Quantitative analyses (synthetic)

| | ROC-AUC | PR-AUC | Brier | Top-10% precision |
|---|---|---|---|---|
| HGB (CV) | 0.675 ± 0.045 | 0.538 ± 0.056 | 0.188 | 69% |
| Logistic regression (CV) | 0.655 ± 0.039 | 0.483 ± 0.061 | 0.196 | 57% |
| Oracle ceiling (CV folds) | 0.709 | 0.556 | 0.181 | 71% |
| HGB (test, 95% CI) | 0.759 (0.682–0.829) | 0.610 | 0.172 | 75% |

- **Calibration:** the mean predicted rate is 29.5% against 29.7% observed. Out-of-fold reliability is within bin noise, and the mean absolute error against the true probability is 0.065.
- **Explanations vs ground truth:**
  - Global importance rank correlation is 0.81.
  - Per-carer SHAP tracks true contributions for tenure (r 0.93), zero hours (0.95) and short-notice changes (0.90).
  - **Split shifts are under-credited** (r 0.13): the model uses the correlated unpaid-gap feature instead.
  - **A null feature, visits per shift, gets small but non-zero importance** (0.047).

**Age audit** (1,000 out-of-sample predictions, top 20% flagged):

| Age band | Observed leaver rate | Mean predicted | Flagged | Ratio to most-flagged |
|---|---|---|---|---|
| 18–24 | 46.8% | 39.7% | 46.8% | 1.00 |
| 25–39 | 31.3% | 31.8% | 25.0% | 0.53 |
| 40–54 | 26.4% | 27.1% | 13.2% | 0.28 |
| 55+ | 23.3% | 25.1% | 8.2% | 0.17 |

Age is not an input. The gap is carried almost entirely by tenure (mean SHAP +0.52 log-odds for 18–24s vs 55+), then short-notice changes and zero-hours contracts. Predictions are roughly calibrated within each band (slightly under-predicting 18–24s), so the model is **accurate and disparate at the same time**.

## Serving (Tiers 3–5)

| | |
|---|---|
| API | `GET /workforce/risk` (ranked list, top 3 factors each) and `GET /workforce/{carer_ref}/explanation` (all factors, support actions, caveats). Manager and coordinator roles only; every read is audited with the carers shown and the model version |
| Scores | Computed on read from a model trained on first use and cached for the process (about 5 s, deterministic, no pickle); not stored. The current workforce is the 200 held-out test carers, so every served score is out of sample |
| Bands | Relative, not absolute: **Elevated** is the top 20% (the support group), **Moderate** is above the team's mean predicted risk, **Low** is the rest (ADR-032). There are no fixed probability cut-offs, because these scores come from synthetic data |
| Explanation units | SHAP log-odds in the API (`log_odds`), plus **percentage points** (`points`) for people: the gap between the baseline and the score, split in proportion to each factor's log-odds, so the rows add up exactly (ADR-034). This is a presentation convention; the log-odds remain the exact values |
| Support actions | Only for factors the provider can change that add at least 0.1 log-odds (about 2 points). Tenure and skills are not provider levers, so they never produce an action. The dashboard adds a "supportive check-in" only for the Elevated band |
| Never served | The label (`left_within_12m`) and the age band |
| Use notice | Returned in every response and shown on every workforce screen |

## Ethical considerations

1. **Punitive use.** The main risk is that a "likely to leave" list is used to deprioritise people: fewer shifts, no training, being "managed out". That would turn a prediction into a self-fulfilling prophecy and be grossly unfair to the carer. Mitigations:
   - prohibited uses are stated in writing;
   - explanations are framed as provider-side levers with a support action;
   - access is restricted to manager and coordinator roles, and every view is audited (Tier 4);
   - an outcome review checks whether flagged carers were offered support, and never whether they were penalised.
2. **Proxy (indirect) discrimination by age.** Young carers are flagged 5.7 times as often as over-55s, through tenure. If flags lead to *support* (mentoring for new starters), the disparity directs help to those who need it, and can be justified as proportionate. If flags lead to anything adverse, it would be indirect age discrimination. Mitigations:
   - publish the age audit with every model version;
   - consider a separate "new starter" programme, so tenure-driven risk is handled by policy rather than by individual flags;
   - re-audit with real data for every protected characteristic that can lawfully be measured.
3. **Surveillance and trust.** Carers may experience risk scoring as monitoring. That calls for worker consultation before deployment, a transparency notice explaining what is used and why, the right to see and contest one's own explanation, and no use of private-life data.
4. **Explanations can mislead.**
   - **Credit moves between correlated features.** SHAP explains the model, not the world: split shifts are under-credited because unpaid gaps carry their signal.
   - **Spurious features appear.** The top-risk test carer's explanation includes "paid hours a week" (+0.17), a feature with no true effect.
   - **Mitigation:** reviewers are told explanations are *suggestions to discuss*, not causes, and rota changes are evaluated by outcomes.

## Caveats and recommendations

- **Circularity.** Every number above measures recovery of a mechanism I wrote. It says nothing about real carers.
- **Small-sample uncertainty.** A provider with a few hundred carers will see AUC intervals of ±0.07 or more. Report intervals, and prefer the simpler model when the difference is within the noise.
- **Drift.** Recalibrate at least annually and after policy changes (pay rises, contract reforms). Monitor top-k precision against actual leavers.
- **Label.** With real data, model voluntary leavers only and handle censoring (consider survival models).
- **SHAP mode.** Re-test interventional SHAP on upgrade. It currently fails additivity for HGB in shap 0.54.1.
