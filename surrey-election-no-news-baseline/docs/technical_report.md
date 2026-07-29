# Surrey no-news baseline — technical report

**Stage 1 of the IRP. 29 July 2026.**
Prepared for the supervisor review that the brief places before any news work
begins.

---

## 1. What was asked, and what this is

Build a leakage-safe model that predicts candidate vote share in Surrey county
contests from information available before polling day, compare several
architectures, select one, and export a reusable bundle. Reform UK is the
study party. Reform UK and UKIP must never be merged.

This baseline exists to be beaten. The project's actual question is whether
pre-election news improves prediction of Reform UK's performance, and that
question is only meaningful against a comparator that is as good as election
history honestly allows.

## 2. Data

24 election events over 19 polling days, 343 contests — 262 single-member
divisions and 81 two-member wards — and 1,992 candidate rows: county elections
in 2013, 2017 and 2021, the East and West Surrey elections of 7 May 2026, and
19 by-elections including four recovered from archive listings during this
work. Seat counts and polling dates are validated on every build and pass.

The modelling layer never reads the workbook. `surrey-election-extractor`
publishes a contract of features and targets in **separate files**, which is a
structural leakage control rather than a convention — a model that cannot
reach the target file cannot accidentally train on it.

**Evidence layers.** The shipped model uses **35 predictors: 10 official
values read from a source page, 2 carrying per-row provenance, and 23 governed
derived quantities this project computed.** (39 predictor columns are
classified in total; the four UKIP interaction columns are absent unless the
sensitivity option is on.) That most inputs are derived is not a defect — a
party's county-wide strength cannot be read off a results page — but it means
the model depends more on rules documented in this repository than on
published numbers. Every column's layer and the reason for it are in
`data_quality_report.json`.

**Unknown stays unknown.** No missing previous vote share becomes zero, no
unavailable archive becomes evidence that nothing happened, no unknown becomes
"No". Every nullable predictor carries its own missingness indicator.

**Non-contestation.** A party that did not stand has no row, so nothing states
it scored zero. 6,263 contestation records hold that separately. Reform UK
contested 6 of 81 divisions in 2021 and 81 of 81 wards in 2026.

## 3. Target

`analysis_vote_share` — a candidate's votes over all votes cast in the
contest.

It is fitted as **a multiple of the contest's equal split** (`share ×
candidates ÷ 100`) and inverted afterwards. Every pre-2026 election was fought
in single-member divisions averaging 22.65 per cent per candidate; the primary
holdout is entirely two-member wards averaging 9.75. On the raw scale a model
would train on one distribution and be scored on another. Because shares sum
to 100 in any contest, the transformed target has mean 1.0 whatever the
contest size.

Secondary outputs: predicted rank, predicted elected status by top-*N* on the
known pre-election seat count, and a separately fitted probability of election
shifted in log-odds until each contest's probabilities sum to its seats.

## 4. Splits and leakage

Splits are defined by **polling date**, never by election name, with an
asserted gap between train and test. Two of the brief's requirements then hold
as arithmetic rather than as discipline: a contest cannot straddle a fold
because it has one polling date, and no 7 May 2026 event can reach training
because the primary holdout trains only through 6 May.

- 4 named development folds; 12 rolling-origin folds, one per polling day.
- **Primary holdout:** everything polled 7 May 2026 — East, West, Warlingham —
  as a single period.
- **Secondary holdout:** Haslemere, 7 July 2026, evaluated both without and
  with the May results.

A 64-column audit classifies every published field with the event that first
made it available. 15 fields are prohibited outright. `change_in_vote_share`
is excluded despite looking historical, because it is current minus previous
share and therefore contains the target. An unclassified column stops the
build rather than defaulting to permitted, and a test fails if a prohibited
field reaches the design matrix.

## 5. Architectures, and what selection cost

Three architectures on identical rows, folds and features.

| | | out-of-fold MAE | OOF winner | holdout MAE | holdout winner | Reform OOF MAE | Reform holdout MAE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | regularised linear | 8.97 | 75.4% | 4.75 | 28.0% | 16.11 | 3.26 |
| C | partial pooling | **8.87** | **76.5%** | **4.39** | **42.7%** | 16.13 | **3.21** |
| **B** | **boosted trees (shipped)** | 9.85 | 74.3% | 4.53 | 30.5% | **10.18** | 3.33 |

Selection runs on development folds only, pooled by rows, with two gates
declared in advance: beat the incumbent by more than 5 per cent on Reform
vote-share MAE, and lose on no more than one fold. B cleared both, at +8.3 per
cent.

**The table does not favour the shipped architecture, and this report does not
present it as though it did.** B is the worst of the three on every overall
measure out of fold and behind C on every column of the holdout. It is
selected because the brief names Reform vote-share MAE first and there B is
not marginally but dramatically better — 10.18 against roughly 16.1. The trade
is about one percentage point of overall MAE.

**And the advantage inverts on the holdout**, where B is the worst of the
three on Reform. Switching to C is refused because choosing an architecture on
the holdout spends the holdout, which would leave nothing untouched to measure
the news layer against. The disagreement is published instead. **It is the
first item this review should consider** — see §9.

## 6. Reform UK

| | out of fold | primary holdout |
| --- | ---: | ---: |
| rows | **14** | 163 |
| MAE | 10.18 | 3.33 |
| improvement over an equal split | **+5.0%** | −11.1% |
| observed mean share | | 10.80% |

Out of fold, the shipped architecture is **the first configuration in this
project to beat an equal split on Reform rows**. That figure rests on fourteen
rows and must never be quoted without them; the bundle carries a
`small_sample_warning` flag set for exactly this.

Two mechanisms were found and acted on.

**SHAP showed one feature moving two parties in opposite directions.**
`previous_party_vote_share` contributes +0.0498 to Conservative predictions
and −0.0880 to Reform ones. Adding county-strength features then made the
linear architectures *worse* on Reform — A from 16.7 to 42.6 per cent below an
equal split — which is the same fact from the other side. County strength and
division share move together for almost every party; Reform is the exception,
at 20.67 per cent county-wide from single-member by-elections against 10.80 in
two-member wards. A linear model fits one global slope and drags Reform along
a relationship it does not follow.

**Interaction terms fixed it.** They add no information — every value is a
product of two columns already present — only the ability to hold a second
slope for one party. C's Reform prediction moved from 8.91 to 10.17 per cent
against 10.80 observed. The strongest evidence is that **Architecture B did
not move at all**, its figures identical to the digit, which is what the
diagnosis predicted because a tree already conditions on party. Four columns
that merely happened to help would have moved it too.

**UKIP as a contextual feature was tested and refused.** The brief permits it
only if it improves genuine unseen Reform predictions. It does the opposite:
Reform out-of-fold MAE goes from 10.18 to 15.10, from 5 per cent better than
an equal split to 41 per cent worse, while *overall* out-of-fold MAE improves
from 9.85 to 9.13. The gain is UKIP's own and is paid for by Reform. The
switch is retained, off by default, so the result can be re-run.

## 7. Uncertainty

Every interval is a **contest-level** bootstrap. Contests are resampled, never
rows: shares within a contest sum to 100, so one candidate's over-prediction
forces another's under-prediction, and row resampling would report an interval
far narrower than the data supports.

| | rows | contests | MAE | 95% interval |
| --- | ---: | ---: | ---: | :---: |
| all candidates, out of fold | 792 | 179 | 9.85 | 9.29 – 10.44 |
| all candidates, holdout | 838 | 82 | 4.53 | 4.24 – 4.86 |
| Reform UK, out of fold | 14 | 14 | 10.18 | **7.42 – 12.74** |
| Reform UK, holdout | 163 | 82 | 3.33 | 2.81 – 3.87 |

**The Reform out-of-fold interval spans 5.3 percentage points.** That is the
honest summary of this project's central problem, and the reason selection
pools folds rather than reading one.

Three further sources are named because no bootstrap covers them: the
architecture was chosen from three rather than fixed in advance; the
county-strength pooling rule (three contests, five years) is a judgement call
whose sensitivity has not been run; and 1,200 cohort rows have no out-of-fold
prediction at all, listed with reasons in the bundle.

## 8. Honest limitations

1. **The baseline does not predict 2026 well.** Winner accuracy 30.5 per cent;
   exact seat sets right in 22.0 per cent of wards. The probability model's
   holdout Brier score is 0.1521 against 0.1567 for predicting the base rate
   for everyone — better, by 0.0046, which is barely better than a constant.
   An earlier version of the model card stated it was *worse* than the base
   rate; that was true and is no longer, and the reversal is recorded rather
   than overwritten.
2. **The failure is directional.** Reform is under-predicted (9.35 against
   10.80 observed, from 8.40 before the interaction terms) and the
   Conservatives over-predicted. The model faithfully learned a Surrey in
   which the Conservatives dominated and Reform did not exist.
3. **The central historical predictor is unstable.** 31 of 106 features change
   sign between folds, including `previous_party_vote_share` itself.
4. **The holdout is not blind.** Its metrics were read during development. No
   2026 row entered training and no hyperparameter was chosen against it, but
   the discipline was weaker than the design intended.
5. **Fourteen Reform rows.** Everything in §6's left-hand column rests on them.

## 9. What this review should decide

Three questions are methodological rather than technical, and each changes
what Stage 2 is built on.

**(a) Should Reform vote-share MAE remain the primary selection criterion?**
It is why B ships despite being worse on every overall measure, and the
criterion reverses on the holdout. The alternative — overall MAE primary,
Reform reported as a required secondary — would ship C. **The news layer
trains on the shipped architecture's out-of-fold predictions, so this decides
what Stage 2 is measured against.**

**(b) Is the news sample viable as it stands?** News collection covers a
sample of divisions chosen on 2026 vote shares, and by-elections have no
collection at all. The training set for a news model would be 199 rows with
**one** Reform row. Extending collection to the by-elections is what would put
Reform rows into it.

**(c) Should borough elections enter the study?** They would multiply the
Reform observations available, and the question of whether that is within
scope belongs to the supervisor rather than to this repository.

## 10. Reproduction

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train
```

Everything tunable is in `config/baseline_model.yaml` with its reasoning; the
resolved configuration is written into the bundle, so a bundle records what it
was built with. The six-page interface is:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m streamlit run surrey-election-no-news-baseline/app/streamlit_app.py
```

424 tests. The ones that matter most assert that something fails: a prohibited
field entering the design matrix, a contest split across folds, a 7 May 2026
row reaching training, an unknown value becoming zero, a UKIP block without
its Reform base, a configuration key that does not exist.

---

## Supporting records

| document | what it holds |
| --- | --- |
| [`candidate_model_card.md`](candidate_model_card.md) | the shipped model, in full |
| [`architecture_selection_evidence.md`](architecture_selection_evidence.md) | §5 in detail, including what selection cost |
| [`reform_interaction_terms.md`](reform_interaction_terms.md) | the §6 experiment and the underpowered selection it exposed |
| [`historical_strength_features.md`](historical_strength_features.md) | county history, and the damage before the fix |
| [`ukip_contextual_sensitivity.md`](ukip_contextual_sensitivity.md) | the UKIP run, refused |
| [`candidate_split_and_leakage.md`](candidate_split_and_leakage.md) | §4 in detail |
| [`run_configuration_and_reproducibility.md`](run_configuration_and_reproducibility.md) | the configuration design and a bundle defect found by a clean rebuild |
| [`stage2_feasibility_findings.md`](stage2_feasibility_findings.md) | §9(b) and (c) in detail |
