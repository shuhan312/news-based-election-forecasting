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
does not provide stable evidence that news improves prediction. **This
paragraph describes the pre-enrichment, pre-unblinding state and is kept
as history.** The corpus was subsequently enriched with the by-election
articles (sections 14-15) and the one-time unblinding has now been run:
the confirmatory answer - v1 0 of 12, v2 5 of 12 with four intervals
above zero, no Reform-specific improvement - is section 16, with
descriptive seat-level results in its addendum and the scenario and
exploratory records in sections 17-18.

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

Source: `production_estimability_v1/estimability_report.json`. (The earlier
`residual_feasibility/` diagnostic was removed from main; it remains in the
commit history.)

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
from a 67-article pilot. This chain has been **removed from main** and remains
in the commit history. Its selected columns and high correlations are audit
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
(section 13); the comparison has since been run once (section 16).
Synthetic-news scenario results now also exist
(`synthetic_scenarios_v1/`): they are labelled simulations of the frozen
v2 model's sensitivity, produced after unblinding, and are not evidence
about voters.

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

## 17. Synthetic scenario results (simulations, not evidence about voters)

Source: `synthetic_scenarios_v1/scenario_findings.md` and
`scenario_results.json`; produced by
`src/news_modelling/synthetic_news_scenarios.py` after unblinding, with
every refit coefficient asserted equal to the frozen v2 protocol's
values before any scenario ran. All figures describe the fitted model's
sensitivity to injected hypothetical coverage; none is a claim about
voter behaviour.

Four preset contrasts, ten injected articles each:

1. **Tone is asymmetric.** The same Reform story moved its mean
   predicted share +1.0 points when favourable and -2.0 when
   unfavourable (30-15-day window, combined arm): the fitted
   coefficients weight unfavourable coverage roughly twice as heavily.
2. **Timing trades share movement for seat movement.** The same
   unfavourable Reform story moved shares more a month out (-2.0
   points, 2 seat calls changed) and seats more at the end (-0.8
   points but 8 seat calls changed in the final 72 hours).
3. **Attacking a rival reshuffles rather than transfers.** Ten
   unfavourable Conservative articles left Reform's share almost
   untouched (+0.015) while changing 22 seat calls: contest
   renormalisation redistributes a damaged party's space across the
   whole field.
4. **The local arm's large response measures fragility, not power.**
   The same favourable Reform story produced +2.1 points through the
   national arm (cell held 45 articles) and +7.4 points with 264
   changed seat calls through the local arm - an injection that
   roughly doubles a near-empty cell under a sensitivity-only
   specification. Recorded as thin-cell fragility.

Boundary, restated: the issue axis (a crime- or immigration-focused
story) cannot flow through the frozen specifications, which carry
volume and portrayal features only.

## 18. Post-unblinding exploratory record

**Residual versus joint approach (the design's required comparison).**
Source: `approach_comparison_v1/`; exploratory by construction. Both
approaches were fitted on the 45 v2 election x party cells under the
frozen features and penalty, evaluated leave-one-election-out across the
ten pre-2026 elections. The residual approach had the lower held-out
cell MAE in **16 of 18 specifications**; the joint approach won only the
two 180-91-day cells. Neither approach beat the baseline-only reference
(7.772) in most specifications - consistent with the confirmatory story
that pre-2026 news signal was marginal and emerged only under the full
v2 fit on 2026. The production choice of the residual approach as
principal is retrospectively supported; nothing here is promoted. The
mechanism reading, labelled interpretation: B's freedom to re-weight the
baseline is an extra parameter to estimate on 45 cells, and with a
well-calibrated baseline that freedom buys noise rather than correction;
A also remains the cleaner measurement of news increment, because any
improvement under A can only come from news, whereas B can improve by
rescaling the baseline and let that read as a news effect.

**Haslemere secondary evaluation: verified already delivered.** The
Stage 1 bundle's `metrics.json` contains both design-required variants:
`secondary_holdout_haslemere_before_may` (MAE 4.47, winner and seat-set
accuracy 1.0, no 7 May information) and
`secondary_holdout_haslemere_after_may` (MAE 7.32 after deliberate
retraining through 7 May - the retrained variant scored worse, on a
four-candidate contest where the difference sits within small-sample
noise; recorded, not interpreted). A
news-side Haslemere evaluation was never built because the news layer
excludes holdout-period by-elections; its 379 collected articles remain
available for exploratory use.

**The two failed portrayal-adjacent layers, and their revival path.**
`credit_blame` (frozen kappa 0.521/0.516; binary redesign scored worse)
and `consequence` (frozen 0.259; redesign 0.598 against the 0.600 bar)
each spent both permitted rescue attempts and remain excluded (section
4; `EXCLUDED_LAYERS` in the extraction runner). Any revival would
require a NEW gold-standard sample - the by-election corpus can supply
one - and would be exploratory only; the deferred decision recorded
here is that no third attempt has been made.

**The two pre-declared decompositions have now been run**
(`exploratory_decompositions_v1/`; exploratory, pre-declared above).
Attribution: refitting the v2 variant without its seven Reform cells
(45 to 38) shrinks every confirmatory improvement substantially and
eliminates two of the five outright (national 90-31 days +0.268 to
-0.002; combined final-72-hours +0.188 to -1.133), while three survive
at reduced size (combined 90-31 days +0.240 to +0.077, combined
30-15 days +0.134 to +0.033, national 14-8 days +0.005 to +0.003).
**Both changes contributed; the Reform-era cells carried the larger
share of the improvement.** Mechanism: in the pooled decomposition the
bias term is pinned near zero by contest normalisation, so party-level
corrections surface as dispersion; dispersion falls in exactly the
mid-range windows where MAE improved and rises where it worsened,
which is consistent with the tide-gauge reading in its pooled form.
The sharper per-party bias decomposition is declared here and not run.

**Reform-specific seat calls, specification by specification
(descriptive addendum).** Computed from the frozen v2 prediction file's
`news_predicted_elected` flags against observed outcomes - the same
frozen artefacts and already-unblinded results the annex reads; no
model was touched. Reform won 14 of its 162 contests. The baseline
predicted 0 Reform seats (row accuracy 0.9136 - exactly what an
all-"lose" call scores). Eleven of the twelve v2 confirmatory
specifications leave every Reform seat call unchanged at 0 predicted:
their share adjustments never lift any Reform candidate over a winning
threshold. The twelfth (combined, 14-8 days - a specification whose
share MAE was harmful) over-corrects to 105 predicted Reform seats,
catching 8 of the 14 real winners inside 97 false positives (row
accuracy 0.3642). The overall seat-accuracy gains recorded at
unblinding (up to 0.8558) therefore came entirely from non-Reform
parties. This is the mechanism finding made concrete on the central
party: a party-level broadcast adjustment either moves no Reform
candidate over the threshold or moves nearly all of them - it cannot
locate WHICH fourteen wards break through, because that information is
ward-geographic, precisely the dispersion term a tide-gauge correction
cannot touch.

**The declared per-party bias decomposition has now been run**
(`exploratory_decompositions_v1/`, findings section 2b; exploratory).
With the pooled pinning removed the tide-gauge mechanism is confirmed
exactly: in the headline 90-31-day specifications every one of the
five supported parties moves its election-wide level error by more
than 0.05 points and not one moves its ward-level dispersion by that
much. The v2 gains are located: Conservative and Liberal Democrat
level corrections (absolute bias falls 1.74 and 2.76 points in the
combined arm). The central party moved the wrong way: the baseline
under-predicted Reform's level by 1.35 points, and every improving
window deepened that error (to -3.16 at 90-31 days, -5.96 at 180-91
days) while combined 14-8 days overshot to +5.16 - the same
specification whose 105-seat Reform over-call the previous addendum
recorded, giving the two addenda one consistent story. Reform's
dispersion never moved from 3.17. The Reform failure is therefore
fully decomposed: news corrected the realignment parties' levels; with
only seven Reform-era training cells it could not move Reform's own
level in a stable direction (the sign flips across windows); and it
touched no party's geography.

**The Haslemere probe: stages 1-4 executed, E5 pass pending
(exploratory case study).** The one post-holdout by-election with
contest-targeted news - Haslemere, single-member, polling day 7 July
2026; Conservative, Liberal Democrat, Reform UK and Green candidates -
is the one setting where party grain IS ward grain, and the baseline's
failure there is Reform-shaped in the opposite direction to May: the
before-May variant over-predicts Reform 17.55 against 8.60 observed
(+8.95; contest MAE 4.47) and retraining through 7 May worsens it to
23.23 (+14.63; MAE 7.32), both variants still calling the Liberal
Democrat winner. The probe asks whether pre-polling news carried the
ward-level signal history missed, using frozen code end to end and
training nothing. Stages 1-3 (`run_haslemere_probe_stages.py`) judged
its 379 collected records with the byte-identical frozen rules: 92
fell to E1, 238 to the 180-day window (E2), 2 to E3, leaving a 47-row
pool - all local-arm, zero Reform-flagged, disjoint from the
enrichment population by assertion. The national arm contributed no
eligible in-window article, so combined-arm specifications will carry
any signal and national-arm specifications will sit near baseline.
Stage 4 (`run_haslemere_probe_llm_batch.py`) ran the frozen v2
eligibility classifier by batch over the pool (47 requests; 3 schema
errors resubmitted; final 47 of 47 ok): E4 excluded nothing, E8
excluded 2, E6 not applicable throughout. The 45 survivors form the
human E5 queue (`e5_local_review_queue.csv`) - E5 stays a human
judgement per the failed validations recorded in section 3 (kappa
0.1911 then 0.4762 against the 0.6000 bar) - and that pass is pending.
No principal or enrichment artefact was touched; all probe outputs
live under `news_collection/haslemere_probe/`.

**The Haslemere probe: completed and scored.** Stage 5 assembled the
human E5 pass (45 rows, reviewer SL; imported external sheet sha256
4fbe4079008cfed4363132c4c5bf97dcf025709cc0450b4b7b1edb676e492b1f;
20 include / 25 exclude, both second reviews resolved to exclude with
reasons on the sheet) with the LLM's E4/E8 verdicts under the frozen
assembler - 45 of 45 resolved, no pending rows. Stage 6 extracted the
20-article corpus with the production model assignment (issues on
Sonnet 20/20 with one second-attempt recovery; revised stance on Haiku
3/3 - seventeen articles name no study party; revised framing on Haiku
20/20). The corpus census: all 20 articles local-arm, windows
8/5/3/1/2/1 from 180-91 days to final-72-hours. Feature rows were
built by the frozen builder over the one-election grid (60 rows,
role test, never fitting input), and the twelve frozen confirmatory
specifications - coefficient-asserted against the v2 protocol before
each run - predicted the contest from the before-May baseline rows
with outcome columns stripped.

Result (probe_result.json / probe_findings.md): news beat its
recalibrated control in **3 of 12** specifications. The window pattern
of the 2026 unblinding REPLICATES on this unseen contest: combined
90-31 days is again the best specification (contest MAE 4.290 against
4.491, the only improvement beyond noise) and 180-91 days is again
harmful, catastrophically so in the combined arm (8.418). On the
central question the answer is sharp: **Reform's +8.95 over-prediction
stays essentially untouched in every specification** (best +8.58,
worst +9.21), because the ward-dense corpus carried almost no
party-political content - 3 of 20 articles name any study party. For
this contest, ward grain did not rescue the news layer: the positional
signal was absent from the local stream itself, not lost to feature
grain. Every specification still calls the Liberal Democrat winner the
baseline already called. Single contest, four candidates: illustrative
evidence only, and the replication of the 90-31-day/far-window pattern
is the probe's most report-worthy observation.

**Collection-gap audit of the Haslemere "no party signal" finding.**
Challenged (correctly) with "could the absent signal be a collection
problem rather than a coverage fact?", the probe's biggest funnel hole
was audited: the 92 records excluded for unresolvable dates (E1 - a
quarter of the collected 379). 54 of the 92 carry political terms.
Their composition, from the stored records: 34 are candidates' own
social-media posts (Facebook/Instagram, several on polling day or
after), 2 are leaflet-archive scans, 1 a party site, and the 19
remaining "news-or-other" URLs are civic databases and non-press pages
- WhoCanIVoteFor candidate listings (including "The 4 candidates in
Haslemere" for 7 July - a Democracy Club database page, not an
article), council election-notice and results pages, a town-council
staff bio, a tactical-voting campaign site (stopreformuk.vote's
Haslemere page), a vote-forum thread, a public-notice portal, a topic
index page, and two pages of an American namesake ministry. **Zero of
the 54 are editorial press articles about the July campaign.** The
query log shows the sharpest possible searches ran (each candidate's
name AND Haslemere, party AND Haslemere, "Haslemere AND by-election",
matching the supervisor's own query template): they surfaced the
campaign's self-published digital trail and no press trail. The
refined conclusion is therefore stronger, not weaker: the local press
genuinely did not cover the campaign, while the campaign WAS visible
in non-news channels (candidate social media, civic databases, a
tactical-voting site) that sit outside the design's news-article
definition (I4/E8). Recorded limitations that stand: village-name
queries (Shottermill, Grayswood) were not run separately from
"Haslemere"; the national arm produced no eligible article for this
contest; 67 quarantined retrieval failures were not content-audited.
The non-news digital trail is a future-work data-source class, not a
usable input under the frozen protocol.

**Correction and catalogue of the non-news trail.** The audit
paragraph above reported "54 of the 92" politically-flagged undated
records while its own composition list (34 + 2 + 1 + 19) sums to 56:
the headline count had used a 200-character extract window, the
composition a 300-character one. The catalogue module
(`catalogue_haslemere_nonnews_trail.py`, outputs beside the probe
files) recounts under the wider window and 56 is the durable figure -
34 candidate/party social-media posts, 7 council or government pages,
6 civic-database pages (including WhoCanIVoteFor's July listing of all
four candidates), 2 leaflet-archive scans, 2 namesake false positives
(an American ministry matching a candidate's surname), and one each of
party site, press topic-index page, public-notice portal,
tactical-voting site (stopreformuk.vote's Haslemere page) and
discussion forum. Editorial press articles among them: still **zero**,
so every conclusion drawn from the audit stands unchanged. The
catalogue is descriptive only - nothing re-enters any corpus or model;
it exists so the "signal lives in non-news channels" finding is a
citable table rather than a paragraph.

**Quarantine audit: the last closable hole, closed.** The 67
quarantined Haslemere records - listed as un-audited in the
collection-gap limitations - have now been content-audited. All 67
were quarantined by one schema technicality (a field holding [] where
the schema requires string-or-null), not by content; none carries any
political term in headline or URL, and none sits on a press domain.
The "no press coverage of the July campaign" finding therefore
survives its second audit. Of the limitations recorded earlier, one
check was considered and deliberately NOT run: manual site searches of
the three main outlets, because the Farnham Herald archive was already
swept by the Wayback CDX route and a clean result could not change any
report wording while the print-only hole necessarily stays open. The
remaining uncertainty is confined to print-only publication and search
-index gaps, both recorded; no further collection verification is
planned for this contest.

**Report table pack v1 built (derived artefact, no new findings).**
`outputs/report_tables_v1/` renders eighteen report-ready tables from
the committed artefacts this register indexes - the unblinding record,
the decomposition, approach-comparison, probe, scenario and catalogue
results, the frozen v2 prediction file, the Stage 1 holdout file and
the canonical v2 release. The pack introduces no number this register
does not already carry; its two recomputations (Reform seat calls,
baseline descriptives) reproduce figures recorded above, its README
states why the two baseline figures (4.514 all-rows / 4.441
supported-party rows) coexist, and its manifest.json records the
sha256 of every input read. Built by
`src/news_modelling/build_report_tables.py`; regenerate with one
command after any upstream artefact changes.

**E5-local backlog triage built (planning artefact; judges nothing).**
The local arm's path to reportability is now costed instead of vague.
The E5-local triage script (removed from main; in commit history)
reproduced the frozen builder's reporting-gate arithmetic (distinct
training values per period, bar 10, verdict = max across all twelve
periods) over the committed v2 table and inventoried all 1,576 unjudged
rows (1,060 principal-extension, 426 by-election
local, 90 second-review). Findings: the cheapest crossing is the
previous_180_days snapshot, where local_party_article_count/share
stand at 9 of 10 - one new distinct value crosses - and all eight
by-election train elections sit at zero local coverage, so any
admission there flips an election from flat to contributing. Rows are
tiered by what judging buys (gate-flip by-election rows smallest-pile
first: caterham-valley 3, hinchley-wood 6, weybridge 14,
guildford-south-east 15 = a 38-row opening move with four independent
crossing chances - an initial count said 39, but one
guildford-south-east row belongs to the second-review queue and is
not yet judgeable; then 2017 fit+gate depth 177; 2021 fit-only 300;
2026 test-side 203; 2013 gate-only 380; second-review 90). The
tier-tagged queue preserves the review-sheet shape. Distinct-value
gains are upper bounds until extraction places admitted articles; any
downstream local rerun is exploratory by construction, the unblinding
having already occurred.

**The v3 exploratory lineage: the local gate has crossed.** The
reviewer's 38-row opening pass (imported sheet sha256
fc9155d597684928fb14..., reviewer SL) admitted 30 articles across all
four target by-elections (caterham-valley 3 of 3, guildford-south-east
13, hinchley-wood 2 with four insufficient-evidence rows, weybridge
12; one guildford-south-east row remains at needs_second_review). The
decisions flow through a PARALLEL v3 lineage - a patched copy of the
review sheet, assembled beside the frozen files - because the v2
release's identity hashes its decision inputs and must stay sealed:
v3 assembly resolves 1,002 of 1,412 rows, 656 includes = the frozen
627 plus 29 new (one human include stays excluded overall under the
LLM's E4/E8 verdict). Extraction ran on the 29 alone, the frame pinned
by set difference so already-extracted articles cannot be touched:
issues 28 of 29 (one record failed both attempts and is dropped by the
frozen retry rule), revised stance 12 of 12 (twelve of the 29 name a
study party - four times the Haslemere probe's density), revised
framing 29 of 29. The v3 feature table (news_feature_table_v3exp,
release canonical-...-v3exp) then re-ran the frozen reporting gate:
local_party_article_count rises 9 to 11 distinct training values,
local_party_article_share 9 to 15, and with local_net_portrayal and
its share also crossing, usable columns rise 12 to 16 - the first
reportable local columns in the project's history. The exploratory
local re-run against 2026 (fit on v3 cells, local columns, scored on
the already-unblinded outcomes) is the declared next step; everything
in this lineage is exploratory by construction.

**The exploratory local re-run: the arm comparison's final panel.**
With its frozen specification newly reportable, the local arm was
re-fitted on the same 45 residual cells with v3 features and scored
against 2026 by the unblinding's own code path (same contest
bootstrap, same seat allocation). Result: local beats its recalibrated
control in **4 of 6 windows**, three with intervals entirely above
zero - +0.325 [+0.250, +0.403] at 180-91 days, +0.267 [+0.084,
+0.432] at 90-31 days, +0.259 [+0.084, +0.417] in the final 72 hours
- with 30-15 days harmful (-0.659) and seat accuracy reaching 0.8173.
Two readings matter. First, at 90-31 days local now matches the best
confirmatory number (national's +0.268). Second, at 180-91 days the
signs INVERT across arms: local helps exactly where combined and
national harm (-0.575/-0.590), which suggests the arms carry
complementary temporal signals rather than one dominating - the
sharpest available answer to the supervisor's which-arm question, and
an argument that a properly-fed combination is future work rather
than settled. Constraints stated with the result: EXPLORATORY (the
outcomes were unblinded before any v3 judgement; the intervals are
descriptive here, not confirmatory); only the training side was
enriched (2026 test-side local inputs unchanged while the 203 tier-4
rows stay unjudged); the local corpus remains small (217 articles).
The confirmatory verdict (v1 0/12, v2 5/12) is untouched.

**Warlingham 2026 scoping note: the last unseen contest, and how its
blindness was spent.** Scoping "is any outcome still unseen?" found
the Warlingham 7 May 2026 by-election (single-member, polling with the
principal election): excluded from HOLDOUT_ELECTIONS, therefore never
scored at unblinding and never touched by any news artefact - but with
essentially no collected news (2 records against Haslemere's 379). On
2 August 2026, during that scoping, the analyst printed the contest's
observed shares from the holdout file; its outcomes are therefore
EXPOSED as of that date, and no specification frozen afterwards can
claim pre-outcome registration against it. Any future Warlingham work
is exploratory-tier, like Haslemere. One descriptive observation is
recorded from the exposure, because it is baseline-side and already
computed in the committed bundle: the baseline UNDER-predicted Reform
there by 18.8 points (13.2 predicted, 32.0 observed) - the opposite
sign to Haslemere's +8.9 over-prediction - so the two 2026 by-elections
bracket the baseline's Reform failure in both directions. The
scoping's first conclusion - that no unseen outcome remained - was
WRONG, corrected the same day by its second stage below.

**Scoping, stage two: Woking South 2025 found news-blind.** The
casual-vacancy trail led to a ninth pre-holdout by-election the news
registry never listed: Woking South, 10 July 2025 (resignation of
Will Forster). Verified with outcome-safe queries only (election ids
and split labels; no observed column was read or printed): the Stage 1
bundle holds five candidate rows WITH an out-of-fold baseline
prediction (rolling_2025-07-10); the election appears in no news
artefact - not in BYELECTION_POLLING_DAYS, not in FIT_ELECTION_MAP,
never at unblinding - because its 27 logged search queries produced no
persisted records, which silently left it outside "the eight
by-elections with collected news". Its outcome is therefore
news-blind AND analyst-blind, one tier above Haslemere/Warlingham
(caveat, to be carried by any use: baseline-informed - the result sat
inside Stage 1's rolling-origin machinery). A live check found no
scheduled future Surrey county by-election (Democracy Club current
elections list and the county elections page, 2 August 2026). The
proposed use - freeze the window-weighted combination and arm
protocol first, collect its 180-day window afresh (all historical
dates), run the frozen funnel, predict, then unseal the result once -
awaits the reviewer's go/no-go against the writing deadline; a
stop-loss (abort and record if usable articles fall short of the
Haslemere scale) is part of the proposal.

**Woking South blind test: protocol frozen before contact.** The
freeze-first step has run: `woking_south_blind_protocol.py` derived
the window-weighted combination mechanically (each window served by
the arm with the largest committed 2026 delta there; ties at 4 dp to
alphabetical order), yielding local for 180-91 days, 14-8 days and
the final 72 hours, national for 90-31 and 7-4 days, combined for
30-15 days - the full delta table sits beside the assignment in
protocol.md. protocol.json pins by sha256 every input the test will
fit or read (both feature tables, the estimability audit, the
out-of-fold file, both result records), pre-declares the endpoints
(primary: combination contest MAE vs baseline; reference: each single
arm; secondary: winner call and per-party signed errors), sets the
stop-loss (abort and record if usable articles < 15) and machine-
locks the unseal: one named script is the only permitted reader of
this contest's outcome columns, and it must find a predictions file
whose exact bytes are already in git history before it will run. No
article has been collected at freeze time.

**Woking South blind test: pre-outcome corpus census and its
consequence, recorded before any prediction exists.** The funnel
resolved 452 of 459 rows; 272 articles are usable (13 local by the
reviewer's E5 pass - notably zero L1 among the includes - and 259
national via the LLM E5 column, per the production rule; two second
reviews resolved to exclude by the reviewer; 5 rows lost to twice-
failed LLM requests and 2 local rows unresolved, all recorded). The
stop-loss (minimum 15) passes with room. The window census, however,
is one-sided: ALL 272 usable articles fall in the 180-91-day window
(January 173, February 99, March-July zero). The mechanism is the
frozen collector's own deterministic cap - the Guardian adapter reads
two pages of fifty, oldest first, so a window with more than a
hundred hits per query saturates at its oldest end - the same
mechanism behind the principal corpus's long-recorded far-window
skew, faithfully reproduced because the protocol pinned the pipeline
unchanged. Consequence, stated before unsealing: the five near
windows will carry structural-zero features, so their specifications
(and the combination's near-window assignments) will behave as
near-null controls; the informative panel of this test is the
180-91-day window, which the frozen combination assigned to the
LOCAL arm. Extraction is in flight (batches wokingsouth1: issues on
Sonnet, stance 218 of 272 naming a study party, framing all).

**Woking South blind predictions written and frozen (still no outcome
read).** `woking_south_blind_predict.py` re-verified every protocol
pin, loaded the contest's five candidate rows with outcome columns
stripped at load, fitted each arm's frozen specification on its
pinned table (combined and national on v2, local on v3exp, the same
45 residual cells), and wrote all 90 prediction rows - 18
specifications, the derived combination marked by pick flags, nothing
selected. The module refuses to overwrite its output; the manifest
records the predictions file's sha256. On the informative panel the
census pre-identified (180-91 days, assigned to LOCAL), the
combination predicts: Liberal Democrats 43.66 and elected,
Conservative 29.63, Labour 11.83, Green 10.26, Reform UK 4.62. The
unseal script exists and is machine-locked: it compares the
predictions file's bytes against the blob committed at HEAD and
refuses to run on any mismatch, so the order predictions-then-outcome
is enforced by git itself, not by promise.

**Woking South unsealed: the blind test refuted the transfer.** The
unseal ran once, against predictions verified byte-identical to the
committed blob c22c0a326dabcb43. On the pre-identified informative
panel (180-91 days) the protocol's pick - the LOCAL arm - scored
contest MAE 13.889 against the baseline's 10.085 (-3.804, the worst
of all eighteen specifications), while the two arms the frozen rule
rejected both beat the baseline (national +0.873, combined +0.719).
Reform UK took roughly 19 percent; the baseline under-predicted it
(12.28) and the local news adjustment pushed it the wrong way to 4.62
(signed error -14.38). The five near windows behaved exactly as the
pre-outcome census predicted - structural-zero controls within 0.32
of baseline - and the combination's picks beat the baseline in 2 of 6
windows, both trivially small near-window positives. All eighteen
specifications called the Liberal Democrat winner. Readings, in the
protocol's own no-promotion terms: the 2026-derived far-window
advantage of the local arm did NOT transfer (2026: national harmful
-0.59, local helpful +0.33; this contest: national helpful +0.87,
local harmful -3.80 - the signs swapped contests), so the arm-window
pattern behind the window-weighted combination is unstable across
contests and the combination hypothesis is refuted at first blind
contact; a 13-article single-contest local corpus can inject large
wrong-direction adjustments, and news mis-signed Reform for a third
time in a third setting (located nowhere in 2026, over-corrected at
Haslemere, crushed to 4.62 against ~19 here). The test's design did
its job: a plausible, mechanically derived, data-driven rule failed
out of sample under a protocol that made failure visible - which is
the argument for one-time unblinding and no-promotion stated as an
experiment. Case study, one contest, five candidates; nothing here
joins or revises any confirmatory verdict.

**Post-unseal autopsy of the pick's 3.804 gap (descriptive, from the
unsealed data).** The contest was a Liberal Democrat landslide no
information source encoded: LD took 64.0 (baseline 45.5), the
Conservatives collapsed to 10.0 (baseline 24.2), Reform took 19.0
(baseline 12.3). Decomposing news-minus-baseline MAE by party: Reform
contributes +1.53 (pushed down to 4.62 while reality surged),
Conservative +1.09 (pushed up to 29.63 while reality collapsed),
Labour +0.67, Liberal Democrats +0.37, Green +0.15 - the local news
adjustment worsened ALL FIVE parties, steering against the realignment
on both of the contest's biggest movers. The baseline's own 10.085 is
itself dominated by the landslide (LD error 18.5, Conservative 14.2):
neither election history nor January-February newspapers carried any
trace of a July landslide, which is the information-availability
reading of this contest stated in arithmetic.

**Turnout: the precise scope record.** The first supervisor email
lists turnout among ten eventual prediction targets; the later
operative brief (the twelve-deliverable email) narrows "what we're
predicting" to vote share, ranking, winning and win probability, and
turnout does not appear in it. The register's earlier one-line reason
("the leakage rules class it as known only after the fact") is
precise about turnout as an INPUT - current-election turnout is
outcome-side and is excluded by the leakage audit - but the reason
turnout was never a modelled TARGET is the operative brief's
narrower target list, not leakage. Both halves are now stated.
Building a turnout model remains possible (turnout per contest is in
the election database, 2013 cross-validated against Wikipedia per
the recorded decision) and would be a new exploratory target if ever
wanted; it is not scheduled against the writing deadline.

**Uncertainty annex to the per-party decomposition: contest-bootstrap
intervals on both islands.** The per-party tide-gauge split (2b) was
recorded as point estimates on the unsealed 2026 outcomes only. The
annex (`per_party_bootstrap_v1/`; module
`news_modelling.per_party_bootstrap`; exploratory, promotes nothing)
recomputes it with contest-level bootstrap intervals - 2000 resamples,
seed 20260728, the primary experiment's own constants, draws paired
across parties so the Reform-versus-group contrast carries its own
interval - and replicates the split on the only other candidate-level
island the news layer owns, the frozen 2021 validation predictions (18
specifications there, 12 on 2026; the 2026 point estimates were
asserted cell-by-cell against the committed decomposition results, 240
cells, zero drift). Both controls are kept; the recalibrated control
is quoted, because in structural-zero windows the baseline control
measures only the recalibration itself. What the intervals add: the
2026 reading survives uncertainty - the legacy level corrections
(Conservative -1.70 [-1.74, -1.64], Liberal Democrat -2.75 [-2.79,
-2.72] in combined 90-31 days) and Reform's worsening (+1.84 [+1.81,
+1.86]) all exclude zero, no 90-31-day dispersion change exceeds 0.07
(largest across all twelve specifications 0.34), and the
Reform-minus-group contrast is positive with an interval excluding
zero in 8 of 12 specifications, the one starred negative being
national final-72-hours at -0.12 [-0.14, -0.00]. On 2021 the
mirror is now also interval-backed: Reform's apparent level
improvements (section 11's extrapolation artefact - zero Reform
fitting rows) are large and stable within the island (-9.14 [-9.61,
-8.70], combined 90-31 days) while the combined and local arms'
7-to-4-day windows swing the contrast to +10.3 (the national arm
carries no 7-4-day signal), and the contrast SIGN FLIPS between
islands (negative in 12 starred 2021 specifications, positive in 8
starred 2026 ones). Census: 2021, of 108 party x specification level-change
intervals, 24 exclude zero improving, 50 worsening, 34 straddle; 2026,
of 60: 23, 16, 21. Two footnotes the tables force. First, a constant
per-party shift cannot move dispersion at all, so every starred
dispersion cell measures the clip-and-renormalise step - the
prediction arithmetic's only ward-dependent operation - not news
content reaching geography: on 2026 the leak is negligible (21 of 60
cells starred, largest 0.34), but in the 2021 windows where the
borrowed adjustments were enormous it is not (26 of 108 starred,
Conservative +20.8 in the local arm's 14-8-day window). That bounds
how far "levels move, geography does not" may be quoted: exact where
adjustments are modest, breached only by clipping arithmetic where
they are wild. Second, the one starred-negative 2026 contrast is
national final-72-hours at -0.12 against positive magnitudes up to
+5.5. Reading, in the register's own terms: the
tide-gauge mechanism survives its uncertainty test on both islands -
levels move, geography does not - and the news layer's Reform level
correction is now interval-backed as unstable in DIRECTION across
islands and windows, the same transfer failure Haslemere and Woking
South recorded, stated for a third time in resampling form. Nothing
here selects a window, an arm or a model.

**Design-resolution annex: the minimal detectable effects behind every
verdict.** The examiner's follow-up to "no improvement" is "how small
an improvement could this design have seen?" - without the number, the
null over-reads. The annex (`minimal_detectable_effect_v1/`; module
`news_modelling.minimal_detectable_effect`; exploratory, promotes
nothing) derives it from the WIDTH of every committed contest-bootstrap
interval - the observed delta never enters the arithmetic, which is
what separates design sensitivity from observed-effect post-hoc power.
258 comparisons, share points, MDE80 = interval half-width x 1.429.
The resolutions: 2021 overall median 0.96 [0.59, 2.63] across the 14
estimable confirmed windows, 2021 Reform-specific 2.60 [0.81, 5.27]
(six Reform contests), 2026 v1 overall 0.36, 2026 v2 overall 0.22
[0.006, 0.58]; the annex's own level readings resolve at 1.63 (2021)
and 0.05 (2026) for Reform's level and 2.33 / 0.29 for the
Reform-versus-group contrast. Per-party level thresholds are computed
for every supported party, and they are NOT interchangeable: in the
2026 headline window they span 0.031 (Labour) to 1.072 (Green), a
thirtyfold range that party size does not explain (Green stood 146
candidates, Labour 126). The driver is the corner |bias| has at zero -
a party already well calibrated has resampled biases folded across
that corner, widening and skewing its interval - so a well-calibrated
party is intrinsically the hardest place to certify a level change.
Read against their own thresholds, the headline window's verdicts
are: 2026 Conservative, Liberal Democrat, Labour and Reform all clear
theirs (Reform in the wrong direction), while Green's +1.05 sits
inside a 1.07 blind zone and cannot be called in either direction;
on 2021 every party clears except Labour (+1.05 against a 3.99
threshold). Reading: the 0-of-18 verdict bounds any
true overall pre-2026 improvement below roughly one MAE point and any
Reform-specific improvement below roughly 2.6 points - "no Reform
evidence" is a statement about resolution as much as about news - and
the 2026 island's 0.22-point resolution is why the small legacy level
corrections could be certified only there. Single-contest case studies
(Haslemere, Woking South) admit no interval and hence unbounded MDE:
the arithmetic form of their illustrative-only status. Caveats
recorded in the findings: normal-approximation SE from percentile
widths; asymmetric intervals flagged per row and used at symmetric
half-width - eleven of the 120 comparisons are flagged and all eleven
sit in the 2021 Reform-specific block, the six-contest corner where
the normal approximation is weakest, so the 2.6-point resolution is
an approximation rather than a sharp threshold; and every figure
conditional on the frozen design, not a general claim about news.
