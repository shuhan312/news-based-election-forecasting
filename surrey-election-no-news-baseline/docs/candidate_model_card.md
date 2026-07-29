# Model card — Surrey no-news candidate baseline

**Bundle:** `candidate_model_bundle_v1`
**Status:** complete for the supervisor's step 4; awaiting the step 5 review
before any news layer is built.

---

## Purpose

Predict each candidate's vote share in a Surrey County Council contest using
only information that existed before polling day. This is the comparator for
the project's actual research question — whether pre-election news adds
predictive value beyond election history — so its job is to be as good as
election history honestly allows, and then to be beaten.

## Target

`analysis_vote_share`: a candidate's votes divided by all votes cast in that
contest.

The model does not fit that quantity directly. It fits **the share as a
multiple of the contest's equal split** (`share × candidates ÷ 100`), and
inverts afterwards. Every election before 7 May 2026 was fought in
single-member divisions and the primary holdout is entirely two-member wards,
so on the raw scale the model would train on contests averaging 4.6 candidates
and 22.65 per cent per candidate and be scored on contests averaging 10.4 and
9.75. Because shares sum to 100 in any contest, the transformed target has
mean 1.0 whatever the contest size: measured on the release, single-member
rows average 1.000 and multi-member rows 1.001.

Secondary outputs: predicted rank, predicted elected status (top-N on the
known pre-election seat count), and a separately fitted probability of
election.

## Dataset

24 election events, 343 contests, 1,992 candidate rows, from the official
Surrey County Council archive and borough returning-officer pages.

- Every row is an eligible prediction target. Rows lacking an approved
  historical predecessor are kept with a missingness reason, not deleted:
  the wards without one are the reorganised ones, so complete-case deletion
  would bias the cohort rather than shrink it.
- 1,042 rows carry an approved previous exact-label party share; 932 have no
  approved area reference; 18 have an approved area but no previous share for
  that party.
- Reform UK and UKIP are separate throughout. No row may set both indicators;
  the release build fails if one does.

### Contestation

A party that did not stand has no candidate row, so nothing anywhere states
that it scored zero. Non-contestation is recorded separately in 6,263
contestation records. Reform UK contested 6 of 81 divisions in 2021 (7 per
cent) and 81 of 81 wards in 2026 (100 per cent).

## Split design

Splits are defined by polling date, never by election name, with an asserted
gap between train and test. Two of the brief's rules then hold as arithmetic:
a contest cannot straddle a fold because it has one polling date, and no
7 May 2026 event can reach training because the primary holdout trains only
through 6 May.

- 4 named development folds from the brief; 12 generated rolling-origin folds,
  one per polling day, stopping before the holdout.
- Primary holdout: all events polled 7 May 2026 (East, West, Warlingham).
- Secondary holdout: Haslemere, 7 July 2026, evaluated both without and with
  7 May results.

## Leakage controls

A 78-field audit classifies every published column and every field the brief
names as prohibited. Of 49 published feature columns only 25 are permitted
predictors; identifiers, provenance, linkage and cohort labels are published
but may not be modelled. `permitted_predictors()` is the single list modelling
code selects from, and `assert_no_prohibited_column()` rejects outcome columns
and identity columns such as `candidate_id`.

An unclassified column stops the build rather than defaulting to permitted.
`change_in_vote_share` is excluded despite looking historical, because it is
current minus previous share and therefore contains the target.

## Architectures compared

| | description | selected |
| --- | --- | --- |
| A | ridge on the transformed target, closed form | incumbent |
| C | same fit, separate penalty on party identity (partial pooling) | no |
| **B** | **LightGBM, shallow trees, early stopping inside each fold** | **yes** |

Selection ran on the **development folds**, never the holdout, and required a
challenger to clear two gates declared before any number was computed: improve
the primary criterion (Reform UK vote-share MAE) by more than 5 per cent, and
lose on no more than one development fold. A challenger with fewer than two
comparable folds is refused rather than passed vacuously.

The criterion is pooled across all four development folds, weighted by rows —
16 row-slots over 14 distinct Reform rows. An earlier version read a single
named fold, which contained three Reform rows and could not separate the
architectures at all; that failure and its correction are recorded in
[`reform_interaction_terms.md`](reform_interaction_terms.md).

- C is not selected: −2.6 per cent, and it loses on 2 of 4 development folds.
- B displaces A: +8.3 per cent on Reform MAE, losing 1 of 4 folds (limit 1).

## Performance

Every figure below is recomputed on the 1,992-row release and labelled with
the architecture that produced it. Holdout figures were **not** used for
selection; they are reported, not acted on.

### Selected architecture (B, gradient-boosted trees)

| | out of fold | primary holdout (2026) |
| --- | ---: | ---: |
| rows | 792 | 838 |
| vote-share MAE | 9.85 | 4.53 |
| relative MAE | 0.44 | 0.46 |
| improvement over equal split | +36.8% | +19.2% |
| winner accuracy | 74.3% | 30.5% |
| exact seat set | 74.3% | 22.0% |

**The holdout MAE of 4.53 must not be read as better than the out-of-fold
9.85.** Two-member wards average 9.75 per cent per candidate against 22.65 in
single-member divisions; relative to their own scales the two are 0.46 and
0.44.

### All three architectures, same rows

Each row is a complete build of that architecture, so every figure is computed
the same way — not a per-fold average standing in for a pooled one.

| | OOF MAE | OOF winner | holdout MAE | holdout winner | holdout seat set | Reform OOF MAE | Reform holdout MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A regularised linear | 8.97 | 75.4% | 4.75 | 28.0% | 19.5% | 16.11 | 3.26 |
| C partial pooling | **8.87** | **76.5%** | **4.39** | **42.7%** | **23.2%** | 16.13 | **3.21** |
| **B boosted trees (shipped)** | 9.85 | 74.3% | 4.53 | 30.5% | 22.0% | **10.18** | 3.33 |

**This table does not flatter the selected architecture, and it is not meant
to.** B is the worst of the three on every overall measure out of fold, and
behind C on every column of the holdout. It is selected because the brief
names Reform UK vote-share MAE as the first criterion and on out-of-fold
Reform rows B is not marginally but dramatically better — 10.18 against
roughly 16.1, a 37 per cent reduction.

The trade is roughly one percentage point of overall MAE for that. And the
advantage does not survive into the holdout, where B becomes the *worst* of
the three on Reform. The complete argument, including why this is not
resolved by switching to C, is in
[`architecture_selection_evidence.md`](architecture_selection_evidence.md).

### Probability of election

Fitted separately by regularised logistic regression, with a per-contest
log-odds shift so probabilities sum to the known seat count.

| | out of fold | primary holdout |
| --- | ---: | ---: |
| rows | 792 | 838 |
| Brier | 0.1179 | **0.1521** |
| Brier, predicting the base rate | 0.1749 | **0.1567** |
| log loss | 0.3819 | 0.4668 |
| log loss, predicting the base rate | 0.5344 | 0.4927 |
| calibration slope | 1.20 | **0.63** |
| expected calibration error | 0.0986 | 0.0652 |
| observed election rate | 22.6% | 19.5% |

**An earlier version of this card stated that on the holdout the model was
worse than telling every 2026 candidate they had a one-in-five chance. That is
no longer true, and the reversal is recorded here rather than quietly
overwritten.** It was true at Brier 0.1591 against a base rate of 0.1567. With
the county-strength features and Reform interaction terms added, the model
reaches 0.1521 against the same 0.1567 — it now beats the base rate, by 0.0046.

That margin is small enough to deserve saying plainly: **on the holdout this
probability model is barely better than a constant.** Out of fold the margin
is real (0.1179 against 0.1749), which is the more familiar pattern of a model
that has learned the single-member by-election setting it was trained in and
transfers poorly to two-member wards.

The calibration slopes tell the same story from the other side. Out of fold
1.20 means predictions are slightly too conservative; on the holdout 0.63
means they are too extreme — the model is more confident about 2026 than 2026
justifies. Ten-bin reliability tables for both are in `metrics.json` under
`election_probability`.

### Reform UK

Figures below are from the current bundle, after the county-strength features
and the Reform interaction terms were added.

| | out of fold | primary holdout |
| --- | ---: | ---: |
| rows | 14 | 163 |
| share MAE (B, selected) | 10.18 | 3.33 |
| improvement over equal split (B) | **+5.0%** | **−11.1%** |
| improvement over equal split (A) | | −8.8% |
| improvement over equal split (C) | | −7.0% |
| observed mean share (holdout) | | 10.80% |

One result deserves separating out, because it changed with the by-election
recovery and was not true before it. **Out of fold, Architecture B is the
first configuration in this project to beat an equal split on Reform UK
rows — by 5.0 per cent.**

On the holdout the ordering reverses: the two linear architectures, once
given the interaction terms, are now *closer* to an equal split on Reform
than the tree is (−7.0 and −8.8 per cent against B's −11.1). The interactions
gave the linear models something the tree already had implicitly, and on the
holdout they use it better. That is the same disagreement recorded under
[Architectures compared](#architectures-compared): development evidence
selects B, the holdout prefers C, and neither is overruled by the other. The
complete three-way comparison across every split role, including the overall
metrics on which B is the worst of the three everywhere, is in
[`architecture_selection_evidence.md`](architecture_selection_evidence.md).

The out-of-fold figure rests on **14 rows**. It is reported because it is what
the data says, and it must not be quoted without the sample size;
`reform_metrics.json` carries a `small_sample_warning` flag that is `true` for
exactly this reason.

## Uncertainty

Every interval below is a **contest-level** bootstrap: whole contests are
resampled, never individual candidate rows. Candidates within a contest are
not independent — their shares sum to 100, so one candidate's over-prediction
forces another's under-prediction — and resampling rows would report an
interval far narrower than the data supports. 2,000 resamples, seed 20260728,
both recorded in `training_config.yaml`.

| | rows | contests | MAE | 95% interval |
| --- | ---: | ---: | ---: | :---: |
| all candidates, out of fold | 792 | 179 | 9.85 | 9.29 – 10.44 |
| all candidates, primary holdout | 838 | 82 | 4.53 | 4.24 – 4.86 |
| Reform UK, out of fold | 14 | 14 | 10.18 | 7.42 – 12.74 |
| Reform UK, primary holdout | 163 | 82 | 3.33 | 2.81 – 3.87 |

**The Reform out-of-fold interval spans 5.3 percentage points.** That width is
the honest summary of this project's central sampling problem: fourteen rows
cannot pin down a Reform error rate, and any comparison between architectures
on those rows is inside the noise. It is also why architecture selection pools
development folds rather than reading one, and why the selection record
publishes how many rows it rested on.

Three further sources of uncertainty are **not** in these intervals, and no
bootstrap can put them there:

- **Architecture uncertainty.** The interval is computed for the selected
  architecture as though it had been fixed in advance. It was not — it was
  chosen from three, on evidence the holdout then contradicted. The true
  uncertainty over "what this pipeline predicts" is wider than any single
  architecture's interval.
- **Feature-construction uncertainty.** The county-strength pooling rule
  (three contests, five years) is a judgement call. Different defensible
  choices give different features and therefore different errors. The
  parameters are exposed in `config/baseline_model.yaml` so the sensitivity
  can be run; it has not been.
- **Coverage, not sampling.** 1,200 cohort rows have no out-of-fold
  prediction, listed with reasons in
  `rows_without_out_of_fold_prediction.csv`. They are absent by design — held
  out, or too early to have anything to train on — but their absence is a
  limit on what the out-of-fold figures describe, not random error around it.

Probability calibration is reported separately, in `metrics.json` under
`election_probability`: Brier 0.118 and log loss 0.382 out of fold, Brier
0.152 and log loss 0.467 on the holdout, with a ten-bin reliability table
beside each.

## Why the model predicts what it does

Exact TreeSHAP contributions for the selected architecture, measured on the
838 holdout rows. Values are on the model's own scale, where 1.0 is the
contest's equal split.

### The Reform UK under-prediction, decomposed

| Reform UK, 163 holdout rows | contribution |
| --- | ---: |
| base value (model's average output) | 0.9962 |
| is an established-category party | **+0.1514** |
| is not the Conservative party | **−0.0969** |
| previous party vote share (low) | **−0.0880** |
| was not the previous winner | −0.0382 |
| is not a local-category party | −0.0370 |
| **final mean prediction** | **0.8932** |

Observed Reform UK performance was **1.11** times the equal split
(10.80 per cent against a 9.75 per cent mean). The model starts at the
average, is pushed up by Reform's party category, then pushed below the equal
split by every historical feature it has — because Reform has no useful
history to be pushed up by. It treats Reform as an ordinary party with a weak
record rather than as a party undergoing a step change.

### The Conservative comparison, which is the mirror image

| Conservative, holdout | contribution |
| --- | ---: |
| is the Conservative party | **+0.4256** |
| previous party vote share | **+0.0498** |
| election year | −0.0918 |
| **final mean prediction** | **1.3861** |

`previous_party_vote_share` contributes **+0.0498 for the Conservatives and
−0.0880 for Reform UK**. The same feature pushes the two parties in opposite
directions.

That resolves a question the linear diagnostics raised and could not answer.
Under Architecture C, `previous_party_vote_share` changes sign between folds
and is flagged unstable — yet Architecture B relies on it more than any other
non-identity feature. Both observations are consistent once the SHAP
decomposition is seen: the feature's effect is conditional on party, a linear
model can only fit one average slope for it, and that average is torn between
folds depending on the party mix each fold happens to contain. The tree can
condition, so it uses the feature the linear model had to discard.

### Gain and SHAP disagree, and the disagreement is informative

| feature | gain rank | SHAP rank | gap |
| --- | ---: | ---: | ---: |
| `candidate_count_in_contest` | 6 | 13 | 7 |
| `analysis_previous_turnout__missing` | 16 | 10 | 6 |
| `is_ukip__true` | 15 | 20 | 5 |

Gain measures how much a feature improved the objective while the trees were
being built; SHAP measures how much it moves predictions on the rows being
explained. `candidate_count_in_contest` is useful for splitting during
training but barely moves the holdout, which is expected: the target is
already expressed as a multiple of the equal split, so contest size has been
divided out of the quantity being predicted.

## Known limitations

1. **The baseline does not predict the 2026 election.** Winner accuracy is
   30.5 per cent against roughly 19 per cent for picking at random from a
   ten-candidate two-seat ward; exact seat sets are right in 22.0 per cent of
   wards; and the probability model's Brier score of 0.1521 beats the 0.1567
   of predicting the base rate for everyone by 0.0046 — a margin small enough
   that "barely better than a constant" is the fair description. The
   calibration slope of 0.63 means the predictions are more extreme than the
   evidence supports.

   Architecture C, which was not selected, reaches 42.7 per cent winner
   accuracy on the same rows. That gap is discussed in
   [`architecture_selection_evidence.md`](architecture_selection_evidence.md)
   and is not resolved here.

2. **The failure is directional.** Reform UK is under-predicted (9.35 per
   cent against 10.80 observed, from 8.40 before the interaction terms) and
   the Conservatives over-predicted; feature
   importance shows why. Measured on Architecture C across sixteen rolling
   folds of the 1,987-row release, the strongest single feature is being the
   Conservative party (+0.216), while Reform's effect is 98.9 per cent
   borrowed from the pooled all-party mean because it has 14 observations. The
   model faithfully learned a Surrey in which the Conservatives dominated and
   Reform did not exist. This diagnostic predates the fourth by-election and
   has not been recomputed on the 1,992-row release; the four rows it adds
   cannot change its direction.

3. **The central historical predictor is unstable.** 31 of 106 features change
   sign between folds under Architecture C, and they include
   `previous_party_vote_share` itself.
   Party identity is stable; historical performance is not. The tree
   architecture uses that feature most heavily, which suggests its
   relationship with the target is non-linear and a single linear slope was
   being torn between folds.

4. **By-elections transfer poorly.** Architecture A picked the winner in none
   of the five 2025 by-elections; B and C reach 57 per cent on that fold. Low turnout,
   short ballots and protest voting make principal-election history a poor
   guide.

5. **No election-cycle or contest random effects.** The target election never
   appears in training, so their estimate for any forecast is the pooled mean
   of zero. Including them would improve in-sample fit and contribute nothing
   out of sample.

6. **Reform UK's party category is doing unexamined work.** The single
   largest positive contribution to Reform's holdout predictions is
   `party_category__established` at +0.1514, which places Reform in the same
   category bucket as the Conservatives and Labour. That classification comes
   from the extraction layer's party-category field, not from the modelling
   layer, and it is questionable for a party that contested 7 per cent of
   divisions in 2021. The model is therefore given a prior that Reform behaves
   like a major party, and then pushed back below the equal split by every
   historical feature. Whether a different category would improve or worsen
   the prediction has not been tested.

7. **Independents are pooled.** The release keeps each independent as a
   separate political identity, but the model sees one `Independent` category:
   a per-individual effect cannot be learned and is not claimed.

## Blinding — a disclosure

The brief asks that predictions be "saved first and only then compared to
reality". That protocol was **not** followed strictly during development:
holdout metrics were computed and read repeatedly while building the
architectures.

What did **not** happen: no 2026 row entered any training set; no
hyperparameter was chosen against the holdout; the architecture selection was
run on a development fold with the holdout withheld.

What did happen: researcher degrees of freedom. Design decisions were taken
by people who had seen holdout numbers. The honest description is that this
is a *reported* holdout rather than a *blind* one, and the secondary Haslemere
holdout should be treated as the cleaner test of the two.

## Intended use

A comparator. The out-of-fold predictions exist so a news layer can be trained
on residuals against a baseline that never saw the row it is being scored on.

## Prohibited interpretations

- These are statistical patterns, not causes. The model does not establish why
  any voter behaved as they did.
- A coefficient or contribution is not an effect size for policy.
- Reform-specific figures rest on 14 pre-2026 observations and must carry that
  caveat wherever they are quoted.
- Nothing here supports claims about individuals.

## Reproduction

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/build_candidate_model_bundle.py
```

Closed-form ridge, a deterministic encoder and a seeded LightGBM make every
figure above reproducible; the only random seed in the pipeline is the
evaluation bootstrap, recorded in `metrics.json`.
