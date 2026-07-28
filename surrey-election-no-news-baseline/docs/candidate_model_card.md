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

Selection ran on a **development fold**, not the holdout, and required a
challenger to clear two gates declared before any number was computed: improve
the primary criterion (Reform UK vote-share MAE) by more than 5 per cent, and
lose on no more than one development fold. A challenger with fewer than two
comparable folds is refused rather than passed vacuously.

- C was rejected: 1.1 per cent improvement, below the 5 per cent threshold.
- B was selected: 22.3 per cent improvement, losing 0 of 4 development folds.

## Performance

Every figure below is recomputed on the 1,992-row release and labelled with
the architecture that produced it. Holdout figures were **not** used for
selection; they are reported, not acted on.

### Selected architecture (B, gradient-boosted trees)

| | out of fold | primary holdout (2026) |
| --- | ---: | ---: |
| rows | 792 | 838 |
| vote-share MAE | 10.04 | 4.78 |
| relative MAE | 0.44 | 0.49 |
| improvement over equal split | +35.5% | +14.8% |
| winner accuracy | 73.7% | 32.9% |
| exact seat set | 73.7% | 23.2% |

**The holdout MAE of 4.78 must not be read as better than the out-of-fold
10.04.** Two-member wards average 9.75 per cent per candidate against 22.65 in
single-member divisions; relative to their own scales the two are 0.49 and
0.44.

### All three architectures, same rows

| | OOF MAE | OOF winner | holdout MAE | holdout winner | holdout Reform vs equal split |
| --- | ---: | ---: | ---: | ---: | ---: |
| A regularised linear | 10.81 | 72.6% | 4.78 | 29.3% | −16.7% |
| C partial pooling | 9.53 | 69.8% | 4.89 | 30.5% | −15.8% |
| **B boosted trees** | 10.04 | **73.7%** | 4.78 | **32.9%** | **−12.4%** |

C has the best out-of-fold MAE and the worst out-of-fold winner accuracy. No
architecture dominates on every measure, which is why selection ran against
one declared primary criterion with declared gates rather than an argmax.

### Probability of election

Fitted separately by regularised logistic regression, with a per-contest
log-odds shift so probabilities sum to the known seat count.

| | out of fold | primary holdout |
| --- | ---: | ---: |
| rows | 792 | 838 |
| Brier | 0.1298 | **0.1591** |
| Brier, predicting the base rate | 0.1749 | **0.1567** |
| log loss | 0.4214 | 0.4928 |
| calibration slope | 0.69 | **0.49** |
| expected calibration error | 0.1050 | 0.0919 |

**On the holdout the model is worse than telling every 2026 candidate they
have a one-in-five chance** (0.1591 against 0.1567), and the calibration slope
of 0.49 means it is confidently wrong rather than merely wrong.

### Reform UK

| | out of fold | primary holdout |
| --- | ---: | ---: |
| rows | 14 | 163 |
| share MAE (B) | 10.27 | 3.37 |
| improvement over equal split (B) | **+4.1%** | **−12.4%** |
| improvement over equal split (A) | −21.2% | −16.7% |
| improvement over equal split (C) | −22.2% | −15.8% |
| probability Brier vs base rate | 0.0702 vs 0.0663 | 0.0893 vs 0.0836 |
| predicted mean share (B, holdout) | | 9.44% |
| observed mean share (holdout) | | 10.80% |

One result deserves separating out, because it changed with the by-election
recovery and was not true before it. **Out of fold, Architecture B is the
first configuration in this project to beat an equal split on Reform UK
rows — by 4.1 per cent.** Architectures A and C remain 21 to 22 per cent
worse than an equal split on the same 14 rows. The advantage does not survive
into the holdout, where B is still 12.4 per cent worse than an equal split,
but it is a real difference between a tree model and a linear one on the
party this project is about.

That figure rests on **14 rows**. It is reported because it is what the data
says, and it must not be quoted without the sample size.

## Known limitations

1. **The baseline does not predict the 2026 election.** Winner accuracy is
   32.9 per cent against roughly 19 per cent for picking at random from a
   ten-candidate two-seat ward; exact seat sets are right in 23.2 per cent of
   wards; and the probability model's Brier score of 0.1591 is worse than the
   0.1567 of predicting the base rate for everyone. The calibration slope of
   0.49 means it is not merely wrong but confidently wrong.

2. **The failure is directional.** Reform UK is under-predicted (9.44 per
   cent against 10.80 observed) and the Conservatives over-predicted; feature
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

6. **Independents are pooled.** The release keeps each independent as a
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
