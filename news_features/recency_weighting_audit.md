# Recency Weighting Audit

Phase 7, Step 6. Version `recency-weighting-v1.0-2026-07-27`.

## 1. Weighting method

Exponential temporal decay, `weight = exp(-lambda *
days_before_polling)`, with lambda expressed as a half-life. Full
formula, justification, worked examples and limitations in
`recency_weighting_method.md`. Weighted counts are summed weights;
weighted proportions use weighted denominators. Lambda was fixed
from campaign-calendar reasoning and a pre-registered grid, with no
contact with election outcomes.

## 2. Parameters used

Primary half-life **30 days** (lambda 0.023105), flagged per row by
`is_primary_half_life`. Grid also computed: 7 (0.099021), 14
(0.049510), 60 (0.011552) and 90 (0.007702) days. Every row carries
its `half_life_days` and `lambda`, so no output is ambiguous about
which parameter produced it.

## 3. Output files

Created: `recency_weighted_features.parquet` (288K, in Git),
`recency_weighted_features.csv` (2.7M - created as required, but
gitignored under the repository's large-file policy; the parquet
holds identical content and the CSV regenerates in seconds),
`recency_weighting_exclusions.json`, this audit and
`recency_weighting_method.md`. Modified: the Step 5 window-expansion
logic was extracted into a shared function so both layers group
articles by one definition; the Step 5 outputs are byte-identical
after the refactor (asserted at build time and by its own tests).
**No previous output file was overwritten.**

## 4. Aggregated records

**2,720 weighted rows x 232 columns** = the 544 Step 5 groups x 5
half-lives. Keys are the Step 5 keys plus `half_life_days`; the
group set matches Step 5 exactly for every half-life (tested), so
local, national, regional and mixed aggregates remain as separate
as before. Total weighted article mass by half-life: 7d 303.5,
14d 347.6, 30d 399.9, 60d 474.9, 90d 526.4 (against 736 unweighted
article-rows) - strictly increasing with half-life, as it must be.

## 5. Validation results

All checks pass:

* recent articles weigh more than older ones (monotonicity across
  the full grid) and all weights lie in (0, 1];
* weighted counts never exceed unweighted counts; total mass rises
  strictly with half-life;
* weighted proportions lie in [0, 1] and are None - not 0 - when
  the weighted denominator is 0;
* aggregation keys are unique and identical to Step 5's groups;
* the Step 5 CSV is byte-identical before and after the build
  (asserted inside the runner, not only in tests);
* the frozen Phase 6 layer hash is unchanged;
* time-window assignments come from the same shared expansion
  function as Step 5, so they cannot diverge;
* no post-polling article contributes (`days_before_polling > 0`
  holds for every article-level row);
* Reform UK / UKIP separation survives weighting;
* rebuild is byte-identical.

Exclusions: **0 articles** lacked a reliable publication date in the
pilot corpus, so `recency_weighting_exclusions.json` is empty and
every row reports `n_articles_excluded_no_date = 0`. The exclusion
machinery is exercised by synthetic unit tests instead.

Test results: 14 new tests in `tests/test_recency_weighting.py` -
**14 passed**. Full repository suite: **567 passed, 0 failed**.

## 6. Limitations

Summarised from the method document: pilot composition (103 of 736
article-rows in the 91-180 day window, mean weight 0.033) makes
weighted pilot aggregates rest on few articles; exponential decay
is an assumption, not an empirical finding; date precision is
day-level; weighted counts are masses, not article counts; undated
articles are excluded rather than imputed. The weighted layer
answers "does recency add predictive value" only once a model
compares it against the preserved unweighted layer - that
comparison belongs to a later step and was not started here.
