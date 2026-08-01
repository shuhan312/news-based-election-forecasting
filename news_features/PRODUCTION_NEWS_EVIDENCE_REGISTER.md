# Production news evidence register

**Evidence cut-off: 1 August 2026.** This document records results that can be
reproduced from repository files. It separates production evidence,
superseded pilot evidence, estimates and work not yet run. A missing result is
not recorded as a negative result.

## 1. Current conclusion

The production corpus contains 1,632 usable articles: 188 local and 1,444
national. It supports a complete 288-row feature table at election × party ×
period grain, not ward grain. Combined and national party features can enter
an exploratory model; local party features can be fitted only as a sensitivity
analysis. A Reform-specific news coefficient is not estimable: the only
principal fitting election with a Stage 1 out-of-fold baseline is 2017, which
has no Reform rows, while 2021 validation has six. No production
news-enhanced score exists yet, so the repository does not yet show that news
improves prediction.

## 2. Evidence-status rules

| status | meaning |
| --- | --- |
| **Production** | derived from the frozen 1,632-article release and current Stage 1 bundle |
| **Validation result** | an observed reliability/gate result; it may pass or fail |
| **Legacy** | audit history, not valid input to the final model |
| **Estimate** | a projection based on stated assumptions, not an observed output |
| **Not run** | no valid result exists; this is not “no effect” |

## 3. Corpus and eligibility results

Source: `news_collection/canonical_corpus_release_v1.json`, release
`canonical-news-v1-59d113bb9c28`.

| stage | total | local | national | interpretation |
| --- | ---: | ---: | ---: | --- |
| main decision table only | 1,452 | 120 | 1,332 | one adjudication stream |
| terminal include union | 1,638 | 188 | 1,450 | all terminal decision streams |
| usable feature corpus | **1,632** | **188** | **1,444** | **Production** |

Six terminal includes were excluded because no usable text exists; all six are
national. The production corpus has 453 articles for 2013, 497 for 2017, 333
for 2021 and 349 for 2026. The six confirmed windows contain 1,302, 241, 32,
32, 11 and 14 articles, oldest to newest. This is coverage imbalance, not
evidence that older news predicts better.

### E5 local-extension experiment

Sources: `llm_v2_local_extension_batch_state.json`,
`e5_local_risk_review_plan.json` and
`e5_local_risk_review_evaluation.json`.

The Sonnet Batch API submission contained 1,037 requests. Together with 23
records without full text, the queue covered 1,060 local candidates. The model
marked 936 as machine-rule-cleared, but the declared method did not permit
automatic admission without validation.

| blind E5 validation result | value |
| --- | ---: |
| reviewed validation rows | 138 / 138 |
| raw agreement | 0.7101 |
| Cohen's kappa | **0.4762** |
| required kappa | 0.6000 |
| model excludes | n=63, agreement 0.9365 |
| model includes | n=75, agreement 0.5200 |
| verdict | **failed** |

The repository audit records the mandatory set as **0/112 completed** and 686
rows as deferred. If a completed external spreadsheet exists, it is not a
reproducible repository result until an import records its hash, decisions and
reconciliation. Therefore the 936 rows were not automatically added, the E5
classifier is not validated, and the production local count remains **188**.
“936 eligible local articles” is not a valid conclusion.

The historical 168-pair E5 pilot also failed: agreement 0.5238 and kappa
0.1911. The newer blind result improved but still missed the gate.

## 4. LLM extraction validation and corpus run

The detailed source is `llm_context/d4_findings_log.md`, which preserves all
16 experiments and marks superseded calculations. Final validator-gated
decisions are:

| layer | final evidence | decision |
| --- | --- | --- |
| issues | human kappa 0.616, Sonnet n=53; inter-model kappa 0.742 | available |
| revised three-level stance | inter-model kappa 0.848; human kappa 0.741 / 0.736, n=71 | available; not five-level sentiment |
| revised incumbent-judgement frame | inter-model kappa 0.705 | available with limitation |
| revised local-impact frame | inter-model kappa 0.635 | available with limitation |
| challenger emergence / voter discontent | only 2–6 / 4–5 positives in 55 | undetermined, not passed |
| consequence | frozen kappa 0.259, n=55; redesign 0.598 on both arms, n=60 | unavailable; below 0.600 |
| credit/blame | frozen human kappa 0.521 / 0.516, n=57; redesign failed to rescue | unavailable |
| Reform mention | deterministic text pattern | available with strict/loose sensitivity forms |

The framing redesign recalled only 49.1–58.3% of the reviewer's chosen frame.
That is construct disagreement, not proof either coder is correct. Sonnet also
produced 5 malformed responses out of 60 in that test; Haiku produced 0/60.

The full run used Sonnet for issues and Haiku for revised stance and framing.
After validator filtering and deduplication it retained 1,604 issue records,
1,187 stance records and 1,632 framing records. Their union covers 1,632 of
1,632 canonical articles. Overlapping tranches would otherwise double-count 98
framing and 66 stance articles; newest-tranche-wins deduplication and a
corpus-size assertion prevent this.

## 5. Geographic-grain experiment

Sources: `article_area_attribution_summary.json` and
`feature_grain_diagnosis.json`.

| route | articles | share of 1,632 |
| --- | ---: | ---: |
| ward-specific query | 46 | 2.8% |
| exactly one area in body text | 22 | 1.3% |
| several areas | 26 | 1.6% |
| no unambiguous Surrey area | **1,538** | **94.2%** |

Only 68 articles have one unambiguous area. Body matching raises attribution
from 2.8% to 4.2%, still too sparse for a general ward feature. The arms differ:
64/188 local articles (34.0%) versus 4/1,444 national articles (0.3%) have one
area. The table can study party/election differences but not differences
between Surrey divisions within an election.

At the 2013+2017 feature split, election-level features have two training cells
and cannot support a reportable coefficient. Election × party features have
ten non-empty cells and are the only viable grain. Those ten cells still come
from only two elections.

## 6. Production feature-table results

Sources: `news_feature_table_v1.csv` and its metadata.

- Dimensions: 4 elections × 6 parties × 12 periods = **288 unique rows**.
- Split rows: 144 train, 72 validation and 72 test.
- Eighteen explicit zero-article rows were previously dropped; the old 270-row
  table therefore converted real zeroes into missing observations.
- Counts are zero in those cells; shares stay blank when the denominator is
  zero because 0/0 is undefined.

Twelve columns clear the ten-value reporting rule: six combined party features
and the corresponding six national features, with 10–11 distinct training
values within a period. Six local party features have only 5–9 and are
`fittable_not_reportable`. The remaining 29 are insufficient.

An earlier calculation pooled variation across all 12 periods and incorrectly
made 29 extra columns appear usable. The corrected calculation operates within
each period; the pooled verdict is superseded.

| arm | frozen features | role |
| --- | --- | --- |
| combined | party article share; net portrayal share | exploratory primary comparison |
| national | national party article share; national net portrayal share | exploratory primary comparison |
| local | local party article share; local net portrayal share | sensitivity only |

Blank selected shares occur only where their recorded denominator is zero.
The audit permits zero substitution only under that named condition, never
blanket imputation.

## 7. Stage 1 overlap and residual feasibility

Sources: `production_estimability_v1/estimability_report.json` and the legacy
diagnostic `residual_feasibility/coverage_diagnosis.json`.

Stage 1 has 792 OOF rows across principal and by-elections. Only 2017 and 2021
principal elections overlap the production news scope.

| election | OOF rows | Reform | UKIP | permitted role |
| --- | ---: | ---: | ---: | --- |
| 2017 | 377 | **0** | 58 | fitting |
| 2021 | 331 | **6** | 5 | one-time validation |

The legacy 67-article ward residual diagnostic built 20 matched rows, all in
2021 and none Reform. Residual mean was 0.05 points, range -13.0604 to 16.1299.
This is coverage, not model performance. Its election-wide branch covered 708
rows including six Reform rows but had only two distinct election values across
two elections, so the feature was collinear with election identity.

Production conclusions:

- a Reform-specific news coefficient is **not estimable**;
- a party-generic 2017-to-2021 adjustment is exploratory only;
- the six 2021 Reform rows must be reported separately with n=6 visible;
- local is sensitivity-only; and
- none supports causal language.

## 8. Holdout and party safeguards

The gate finds zero 2026 rows in Stage 1 OOF data. It derives reserved election
`ESWS-2026-05` from the feature split and does not open the Stage 1 holdout
file. Feature, window, penalty and architecture selection have no route to
2026 outcomes.

Reform UK and UKIP remain separate. UKIP supplies 58 fitting rows in 2017 but
is not relabelled as Reform and cannot create a Reform-specific estimate.

## 9. Legacy evidence

The article-level, context, ward-party and `feature_selection_v1` chain began
from a 67-article pilot. Its selected columns and high correlations are audit
history, not production evidence. A reported training correlation near 0.74
followed screening thousands of candidates concentrated in one election and
must not be cited as predictive value.

The production model must verify release
`canonical-news-v1-59d113bb9c28` and use the frozen two-feature sets above.

## 10. Estimates and results that do not exist

There are 3,122 collected by-election articles that have not passed the six
production eligibility/extraction stages. Text matching finds 425 Reform
mentions. Applying principal-election funnel rates gives an **estimate** of
roughly 213 usable Reform records. This is not an observed count and is not in
the 1,632-article release.

The following results still do not exist:

- a stable window ranking;
- a reportable local-news effect;
- a Reform-specific learned effect;
- a legitimate 2026 performance comparison; and
- synthetic-news scenario results.

These are **not run or not estimable**, not negative findings.

## 11. Completed production news experiment

Source: `production_news_experiment_v1/experiment_findings.md`; row-level
predictions and complete JSON results are stored beside it.

The frozen residual experiment fitted five independent 2017 party rows and
evaluated 279 supported candidate rows in 2021, including six Reform rows. It
used a ridge penalty of 1.0 fixed before validation. Candidate shares were
clipped at zero where necessary and renormalised within each contest. The 2026
holdout file was not read.

The untouched Stage 1 baseline MAE was 7.1585. A training-only mean-residual
recalibration had MAE 7.5872, showing that even the average 2017 correction did
not transfer cleanly to 2021.

Across the 18 confirmed-window comparisons (three arms × six windows), **zero
improved overall MAE over the recalibrated control**. Non-zero changes all
worsened MAE; zero changes reproduced the recalibrated result. Contest-bootstrap
intervals for the non-zero confirmed-window changes were below zero. This is
the current pre-2026 result and must be reported without selecting a preferred
window.

Reform-only errors improved in several windows, worsened sharply in the
7-to-4-day window and were unchanged in zero-signal windows. These six candidate
rows share party-level news values, Reform has zero fitting rows, and many 2021
feature values lie outside their 2017 ranges. The apparent improvements are
therefore extrapolations from other parties, not evidence of a learned Reform
effect.

Two national cumulative sensitivities (`previous_14_days` and
`previous_30_days`) improved overall MAE over both controls. They remain
sensitivity results: they cannot be promoted to primary findings because the
six confirmed windows were the declared main analysis and no 2021 result may be
used retrospectively to select a window.

The honest conclusion is that the frozen confirmed-window features provide no
pre-2026 evidence of incremental overall predictive value in this design. This
does not establish that news has no general effect: the experiment has one
fitting election, five party-level rows and no Reform training observation.
