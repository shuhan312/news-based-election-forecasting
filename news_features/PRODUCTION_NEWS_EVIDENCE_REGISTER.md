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
confirmed-window comparison improved overall prediction in the frozen model,
and leave-one-party-out checks show that even this direction is sensitive to
whether Conservative is present in the five-row fit. The repository therefore
does not provide stable evidence that news improves prediction. Blinded 2026
predictions for every frozen specification are now archived (section 13); the
one-time unblinded comparison has not been run.

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

These are **not run or not estimable**, not negative findings. The blinded
prediction file that the 2026 comparison requires now exists and is frozen
(section 13); the comparison itself remains unrun.

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

## 12. Leave-one-party-out stability result

Source: `production_news_lopo_v1/lopo_findings.md`; complete machine-readable
results are stored beside it.

Each of the five 2017 fitting parties was removed in turn. The unchanged
two-feature ridge model was refitted on the remaining four party rows and all
18 confirmed-window comparisons were evaluated again, producing 90 robustness
comparisons. Cumulative periods were excluded and the 2026 holdout file was not
read.

| omitted party | comparisons | overall improvements | coefficient sign flips |
| --- | ---: | ---: | ---: |
| Conservative | 18 | **6** | 3 |
| Green | 18 | 0 | 4 |
| Labour | 18 | 0 | 2 |
| Liberal Democrats | 18 | 0 | 5 |
| UKIP | 18 | 0 | 4 |

All six apparent improvements occur only when Conservative is removed. Their
MAE advantage over that omission's recalibrated control ranges from +0.0328 to
+0.5350. Across the 90 comparisons, 18 specifications change the sign of one
standardised news coefficient.

| omitted party | arm | confirmed window | full-model difference | omission difference |
| --- | --- | --- | ---: | ---: |
| Conservative | combined | 180–91 days | -1.9277 | +0.3683 |
| Conservative | combined | 90–31 days | -2.0495 | +0.3486 |
| Conservative | national | 180–91 days | -1.7787 | +0.5350 |
| Conservative | national | 30–15 days | -1.3089 | +0.3901 |
| Conservative | national | 14–8 days | -1.7768 | +0.0328 |
| Conservative | local sensitivity | 180–91 days | -0.8687 | +0.1130 |

The remaining **84/90** omission comparisons do not improve overall MAE. The
full 90-row table records the Reform-only difference and coefficient sign
changes; the companion JSON additionally preserves clipping counts and parties
outside each reduced training range. Bootstrap intervals are not repeated in
LOPO because this audit changes the independent training rows, whereas the
primary experiment's bootstrap conditions on the fitted model and resamples
2021 contests. These are different uncertainty questions.

The pre-declared verdict is
`unstable_single_party_omissions_create_improvements`. The six rows are not
alternative models and must not be selected: removing Conservative after
seeing the outcome would be retrospective model selection on 2021. The result
instead shows that five party-level fitting rows are too fragile for a stable
news-effect conclusion. The frozen primary result remains 0/18, but its
generalisability is weak and must be reported together with this sensitivity.

This finding strengthens the case against adding a more flexible news model to
the current data. A tree or boosting model cannot repair the absence of
independent elections or Reform training rows; it would add flexibility to an
already party-sensitive relationship.

## 13. Blinded 2026 prediction freeze

Source: `blinded_2026_predictions_v1/frozen_protocol.json` and
`blinded_2026_predictions_v1/sha256_manifest.json`; produced by
`src/news_modelling/run_blinded_2026_predictions.py` on 1 August 2026.

This is the first and only news-layer opening of the Stage 1 holdout file.
The six observed-outcome columns are stripped at load, the module contains no
metric or comparison code, and the output directory refuses to be rewritten
once written. One caveat is recorded for honesty: the Stage 1 bundle itself
already contains observed 2026 shares and holdout metrics, computed by its
own training run on 29 July. The blind therefore protects the news layer —
no news feature, window, penalty, variant or specification decision has read
a 2026 outcome — and does not claim that no 2026 figure exists anywhere in
the repository. Those bundle figures must stay unread until the declared
unblinding event. The frozen file predicts the 832 primary-holdout candidate rows
of the two 2026 principal elections; the two post-May-2026 by-elections are
excluded because by-elections are scoped out of the news layer.

Every frozen specification is applied under two fitting variants declared
before any outcome is seen:

| variant | fitting rows | Reform rows | role |
| --- | ---: | ---: | --- |
| pooled_2017_2021 | 11 election × party mean residuals | **1** (from 2021) | **primary** |
| fit_2017_only | 5 party mean residuals | 0 | protocol replication, sensitivity |

Pooling follows the supervisor's split (validation folds into training for
the final test) and is legitimate because 2021 selected nothing: 0/18
confirmed-window comparisons improved, and the interpretation rule forbade
selection. 72 specifications (2 variants × 3 arms × 12 periods) produce
59,904 prediction rows with baseline, recalibrated-control and news-enhanced
shares, ranks and two-seat allocations, renormalised to 100 per contest.

The declared unblinding rule: one unblinding event; every specification
reported; the primary confirmatory family is combined and national arms ×
six confirmed windows under pooled_2017_2021 against the recalibrated
control on overall MAE; local, cumulative and fit_2017_only results are
sensitivity; nothing may be selected or promoted after outcomes are seen;
Reform rows are reported separately with n visible.

Integrity anchors (SHA256, recorded at the freeze):

- `blinded_predictions.csv`
  `966e03cd1c54f7de6e9c455fc382263b74e58a2ade3c793522b53394753b6b54`
- `frozen_protocol.json`
  `86dd73b51dfec23f5913141711f568d234980ca1a27f14c387192e600e91468f`

The protocol file also records the SHA256 of all four inputs (feature table,
estimability report, Stage 1 out-of-fold and holdout files), so the frozen
predictions are reproducible bit-for-bit from the recorded inputs. The 20 MB
predictions CSV stays outside git under the large-file rule; the committed
hashes are its tamper evidence.

## 14. By-election six-stage cost walk-through

Source: `news_collection/byelection_walkthrough_v1/walkthrough_findings.md`
and `walkthrough_report.json`; produced by
`src/news_collection/walk_byelection_pipeline.py` on 1 August 2026.
**Nothing was submitted and nothing was spent.**

This replaces the unpriced section-10 estimate with measured figures. Two of
the ten by-elections fall inside the 2026 holdout period; their 381 articles
are excluded outright, leaving **2,741 usable articles (1,748 local / 993
national) across 8 by-elections**, of which **411** mention Reform UK under
the strict deterministic pattern (the earlier 425 included holdout-period
articles).

| scenario | LLM cost (Batch + caching) | manual E5-local | projected includes | wall-clock |
| --- | --- | --- | ---: | --- |
| A: both arms | $12.10–16.49 | ~4.5 h (~175 rows) | ~637 | 3–5 days |
| B: national only | $10.49–14.25 | none | ~572 | 3–4 days |

Rates are measured per arm from principal artifacts (review-pool entry
10.4% local / 88.0% national; include-among-decided 35.9% / 65.4%; stance
validity 81.7%) rather than the blended 61% previously quoted. Expected
Reform training records: **~220 (Estimate)**. The dominant risks are that
E5-local remains manual-only, that the local include rate rests on a
334-row decided subset, and that adapting the six principal-shaped stage
implementations is development time not captured in dollars.

The enrichment decision is not taken in this repository record; if taken,
enrichment becomes a pre-registered model v2 with its own blinded 2026
prediction file under the section-13 unblinding rule.

## 15. Enrichment executed: corpus v2, feature table v2, blinded v2 freeze

Sources: `news_collection/canonical_corpus_release_v2.json`,
`news_features/news_feature_table_v2_metadata.json`,
`news_features/blinded_2026_predictions_v2/`; produced 1 August 2026.

Scenario A was executed with every judgement made by frozen principal
code behind path-only wrappers. The funnel: 2,741 by-election records
assessed, 1,412 cleared the mechanical rules, and the national arm
resolved to **627 includes** against 285 excludes; 426 local rows remain
unadjudicated (E5-local is human-only and was deferred), and 37
twice-failed articles plus 53 borderline verdicts sit in a second-review
queue. Extraction retained 534 valid issues, 527 stance and 623 framing
records; the issues batch was resubmitted once after the account ran out
of credit mid-run, with the outage batch id preserved in the tranche
manifest.

Release `canonical-news-v2-81000bf38785` unions the untouched v1 corpus
(1,632 articles) with the 627 by-election articles. Feature table v2 has
**864 rows (12 elections × 6 parties × 12 periods)**, retaining
zero-coverage rows for the six by-elections whose national funnel ended
empty. Against v1: **Reform training articles 300 (was 0)**, per-party
training variation 22–23 distinct values within a period (was 10–11),
and `insufficient` columns fall from 29 to 4. The twelve reportable
columns are unchanged in identity; local columns remain
`fittable_not_reportable`.

The v2 blinded freeze fits **45 election × party residual cells across
10 pre-2026 elections, including 7 real Reform UK cells** — the
project's first — under the unchanged specification grid (3 frozen arms
× 12 periods, ridge 1.0) and predicts the same 832 blinded holdout rows
(29,952 prediction rows). No 2026 outcome was read. Integrity anchors:

- `blinded_predictions.csv`
  `6016a8d1240310fe5743944d52e099b8967598bb07a401e93f40de1036137c36`
- `frozen_protocol.json`
  `9515de566fd670e2fca8a7970fc47e7fccfd41bb8d6675cac62f37bad659a5e8`

The v2 protocol binds the v1 file hashes into itself and declares one
unblinding event over both: the enrichment's confirmatory family is the
combined and national arms over the six confirmed windows under the
pooled 2017+2021+by-elections variant, reported beside the v1 primary
and the untouched baseline; all else is sensitivity. The 20 MB v2
predictions CSV stays outside git under the large-file rule; the hashes
above are its tamper evidence.

## 16. The 2026 unblinding: the confirmatory answer

Source: `unblinding_2026_v1/unblinding_findings.md` and
`unblinding_results.json`; produced by `src/news_modelling/unblind_2026.py`
on 1 August 2026, after hash verification of both frozen files, with the
scorer itself committed before its first run. **This section is final and
supersedes nothing: sections 11-12 remain the pre-2026 evidence.**

The untouched Stage 1 baseline scored **MAE 4.5140** over the 832
supported-scope candidate rows of the two 2026 principal elections, with
seat-call accuracy 0.7188; on the 162 Reform UK rows it scored **MAE
3.2318** with seat-call accuracy 0.9136.

**v1 confirmatory family (pre-enrichment, pooled 2017+2021): 0 of 12
comparisons improved** overall MAE over the recalibrated control, and 0
of 12 over the raw baseline; most bootstrap intervals lie entirely below
zero. The pre-2026 negative replicated exactly on the held-out election.

**v2 confirmatory family (enrichment, 2017+2021+by-elections): 5 of 12
comparisons improved**, four with contest-bootstrap intervals entirely
above zero — combined 30-15 days (+0.1339 [+0.0949, +0.1689]), combined
90-31 days (+0.2404 [+0.0781, +0.3866]), national 14-8 days (+0.0048
[+0.0008, +0.0090]) and national 90-31 days (+0.2682 [+0.1088,
+0.4110]) — while the 180-91-day window worsened prediction in both arms
(about -0.58). Reform-only errors did not improve under any confirmatory
specification beyond the recalibrated control; the baseline's own Reform
accuracy was already high.

Sensitivity: 4 of 60 v1 and 14 of 24 v2 sensitivity comparisons improved
their recalibrated controls; per the pre-declared rule none may be
promoted.

The registered interpretation, stated at family level without selecting
windows: **news carried no incremental predictive value until the
training data contained Reform-era coverage; with the by-election
enrichment it produced statistically supported overall improvements in
the mid-range windows (roughly 90 to 8 days before polling) and harm in
the earliest window, and it did not improve Reform-specific prediction,
whose baseline was already strong.**

Two honesty notes, recorded before any exploratory follow-up. First,
the v1-to-v2 contrast changed two things at once: the fitting cells grew
from 11 to 45, and Reform-era cells entered for the first time. Which of
the two carried the improvement is **not identified** by the
confirmatory result; the phrase "until the training data contained
Reform-era coverage" describes the contrast that was run, not a proven
mechanism. Two exploratory decompositions are declared here and listed
as **not run**: refitting the v2 variant without its seven Reform cells,
and splitting each party's 2026 error into an election-wide mean shift
against a within-election dispersion component. Second, the mechanism
reading offered alongside these numbers - that party-level news features
act as an election-wide recalibration of relative party levels, and that
Reform's own residual was already near the baseline's floor (MAE 3.2318
against 4.5140 overall) - is interpretation consistent with the measured
pattern, not itself a pre-registered test, and the report must label it
so.

Both families are reported in full; no post-hoc model may claim
predictive status on 2026 (section 13 rule).

**Seat-level addendum (descriptive annex,
`unblinding_2026_v1/descriptive_targets_annex.md`).** The baseline's
0.7188 row-level seat accuracy conceals a directional failure: it
predicted 118 Conservative seats against 30 actual, 6 Liberal Democrat
against 96, and 0 Reform against 14, with only 18 of 81 wards fully
correct — the 2026 realignment is invisible to election history. The
phrase "the baseline was already strong on Reform" therefore holds for
vote shares (MAE 3.2318, mean 9.3% predicted against 10.7% observed) and
fails for seats (none of Reform's 14 predicted). Seat-call accuracy,
recorded in the same unblinding run as a secondary outcome, diverges
from the MAE endpoint: several v2 confirmatory specifications called
seats better than the baseline (combined final-72-hours 0.8558, both
arms 0.8317 at 180-91 days — a window that worsened share MAE). Under
the no-promotion rule these remain secondary results; the divergence of
the two grains is itself a registered finding for the report.
