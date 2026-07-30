# No-news previous-result persistence benchmark

## Research question and role

This benchmark is the first quantitative comparator for the supervisor's
question: whether pre-election news improves prediction beyond previous
election results. It has no fitted parameters:

- predicted party vote share is the approved previous exact-label party share;
- predicted elected party is the previous winner only when that political
  identity occurs uniquely on the current single-member ballot.

Every prediction is an out-of-time carry-forward from an earlier official
election event. Current votes, vote share, outcome, rank, margin and
`change_in_vote_share` are not predictor inputs.

## Evaluation cohorts

The party-share cohort contains 796 rows across 181 approved single-member
areas. All 796 have a governed prior party share and a well-defined current
single-member party-share target.

Winner persistence is evaluated over the full current party ballot for the
same 181 areas, including current parties without a usable lagged share.
This produces 802 party rows. A unique previous winner is present on the
current ballot in 173 areas; 8 areas remain visibly unscored because the
previous winner is absent, generic Independent, or has an unapproved label
identity change. No alternative party is substituted.

## Overall benchmark results

### Party vote share

- Mean absolute error: **9.46 percentage points**.
- Root mean squared error: **13.96 percentage points**.
- Median absolute error: **6.00 percentage points**.
- Mean signed error (`previous - current`): **-3.23 percentage points**.

The negative signed error means that, among the historically matched current
parties in this cohort, direct carry-forward tends to underpredict current
share. It is a descriptive benchmark property, not evidence that every party
gained support.

### Winning party

- Areas scored: **173 / 181**.
- Correct area winners: **136 / 169**.
- Area-level winner accuracy: **79.8%**.
- Party-row accuracy: **90.8%**.
- Party-row balanced accuracy: **86.9%**.
- Party-row macro F1: **86.9%**.
- Hard-decision Brier score: **0.092**.

Area accuracy is the principal intuitive winner metric. Party-row accuracy is
higher because every area contains several correctly rejected non-winning
parties. Balanced accuracy and macro F1 are therefore retained to make the
class imbalance visible.

The persistence rule emits deterministic Yes/No decisions rather than fitted
probabilities. Its Brier score is explicitly labelled `hard`; it must not be
interpreted as a calibration assessment.

## Principal elections and by-elections

The 703 principal-election party-share rows have MAE **9.09** and RMSE **13.46**
percentage points. Their previous-winner area accuracy is **83.3%** over 156
scored areas.

The 93 by-election party-share rows have MAE **12.28** and RMSE **17.26**
percentage points. Previous-winner area accuracy is **47.1%** over 17 scored
areas. This difference is consistent with by-elections being less stable, but
the by-election sample is small and heterogeneous; no inferential claim is made
from these descriptive figures alone.

## Interpretation boundary

This release establishes a transparent minimum benchmark, not the final
no-news model. It does not estimate coefficients, tune hyperparameters, produce
probabilistic calibration, calculate confidence intervals or use 2026
multi-member wards as if they had a single-member party-share estimand.

Every later no-news or news-aware model must be evaluated on the same declared
cohort, or report a separate common-support comparison. A news model does not
show added value merely by using more rows or excluding difficult contests.

## Reproduction

From the repository root:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
```

The command deterministically regenerates row-level predictions, grouped
metrics and the coverage audit without a network request.
