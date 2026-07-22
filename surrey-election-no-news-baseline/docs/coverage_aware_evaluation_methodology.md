# Coverage-aware no-news evaluation methodology

## Purpose

Every benchmark built so far (`previous_result_persistence_v1`,
`equal_share_reference_v1`, `party_historical_mean_reference_v1`,
`ridge_fundamentals_v1`) reports accuracy only on the rows it happens to
score. None of them says what fraction of the full party-contest universe
that is, or why the rest cannot be scored. A headline MAE is not a complete
scientific claim without that context: an accurate model on a small, easy
subset is a different result from an accurate model across the whole
electoral landscape.

This document freezes the coverage-aware evaluation layer built to close
that gap, in three stages: an audit of existing authoritative fields
(Task 1), a reuse-only mapping of those fields into three cohorts (Task 2),
and a join of the cohort layer against real N0-N3 predictions to compute
coverage and error together (Task 3).

## Task 1: audited authoritative fields (no new logic)

| Concept | Authoritative field | Already used by |
| --- | --- | --- |
| Is this row's own party-level history safe? | `baseline_eligibility` | `persistence_benchmark.is_within_share_cohort` |
| Does this row's area have any accepted historical predecessor? | `geographic_reference_eligibility` | `persistence_benchmark.is_within_winner_cohort` |
| Why is a value missing, at finer grain | `previous_party_vote_share_status` | electoral_fundamentals layer (not currently read by N0-N3) |
| Why is the target share undefined | `target_party_vote_share_status` | `no_news_party_contest.py` |

No duplicated or conflicting eligibility logic was found. One documented
finding: the richer `electoral_fundamentals_*` layer (`no_news_baseline/
electoral_fundamentals_previous_party_zero.py`) uses a different, more
detailed status vocabulary for previous-share provenance (e.g.
`observed_zero_across_complete_previous_crosswalk` for a GIS-crosswalk-
proven zero), including a geographic-crosswalk-derived zero-share recovery
route that the raw `no_news_party_contest_features.json` contract N0-N3
actually consume does not include. This is not a conflict - the two layers
serve different consumers - but it means the crosswalk-zero recovery logic
does not currently reach any of the four benchmarks, and any future model
built directly on the electoral_fundamentals release would need its own,
separately declared cohort mapping rather than reusing this one unchanged.

## Task 2: cohort mapping (reuse only)

```text
if baseline_eligibility == "eligible_primary_single_member_party_share":
    cohort = historical_continuity            # Cohort A
elif geographic_reference_eligibility == "approved_historical_reference":
    cohort = party_entry_no_local_history      # Cohort B
else:
    cohort = geographically_non_comparable     # Cohort C
```

No new eligibility condition is introduced. Before writing this rule, the
live release was checked for the one assumption it depends on - that a
party can only have a safe local vote share if its area itself is
geographically safe - and zero rows contradicted it (a numeric
`previous_party_vote_share` value never co-occurs with a geographically
unsafe area anywhere in the 1,603-row release). The three-way split is
therefore an exhaustive, non-overlapping partition of the real data, not
only of the rule as written.

**Live counts**: Cohort A 775, Cohort B 148, Cohort C 680 (sum 1,603).

Cohort B splits into two structurally different reasons, both preserved
verbatim from the existing `baseline_eligibility` string rather than
rewritten: 142 rows are multi-member contests where the single-member share
estimand is not defined by design, and 6 rows are single-member contests
where the specific party's own previous-election label could not be
uniquely resolved.

### A documented judgement call

The extractor's raw party-contest release used by all four models does not
yet include the electoral_fundamentals layer's crosswalk-derived zero-share
recovery (see Task 1). Had it been present, a row with a complete-coverage
crosswalk-proven zero share would not cleanly fit any of the three cohorts
as literally defined (it carries a value, so it cannot be Cohort C; it does
not come from a single administratively-approved predecessor, so it is not
the cleanest reading of Cohort A). Because no such row exists in the data
these models actually consume, this document records the judgement rather
than needing to resolve it: if that recovery route is ever wired into the
N0-N3 input contract, this mapping must be revisited, not silently assumed
to still be exhaustive.

Every model's theoretical eligibility (`eligible_n0_equal_share` ...
`eligible_n3_ridge`) is likewise computed by calling each model's own
existing cohort predicate (`is_within_share_cohort`, `is_within_winner_
cohort`, the `contest_structure == "single_member"` check already used in
`naive_benchmarks.py`, and `regularised_models.py`'s own fold-and-cohort
filter for `ridge_fundamentals_v1`), never re-derived independently.

## Task 3: coverage and error, jointly

### Two coverage denominators

- **Target-universe coverage** = valid predictions / all 1,603 rows (or a
  cohort's rows). Answers: how much of the whole electoral landscape does
  this model actually speak to?
- **Eligibility-conditioned coverage** = valid predictions / rows the model
  is theoretically eligible to predict. Answers: does the model exploit all
  the information its own design says it is entitled to use? A value below
  100% here is a genuine, previously invisible coverage gap, not a
  structural limit the model was never meant to cover.

### Why persistence is restricted to historical-continuity observations

`previous_result_persistence_v1` can only carry forward a value that
exists. Its `eligible_n2_persistence_share` flag is Cohort A membership
exactly, so its eligibility-conditioned coverage is 100% by construction -
this is not a claim that persistence is complete, only that it never
attempts a share prediction outside the one cohort defined to have safe
values for it to carry forward.

### Common-sample vs own-covered-sample MAE

`own_covered_sample_mae` scores each model only on the rows it personally
produced a valid value for - the largest, most flattering sample each model
can claim. `common_sample_mae` (from `model_comparison.compare_models_on_
common_support`, reused rather than reimplemented) restricts every model to
the identical 740-contest intersection every model actually predicted, so a
model cannot appear stronger merely by being scored on an easier or smaller
set of rows. Both are reported side by side; neither is presented alone as
"the" accuracy figure.

### How same-day leakage is prevented

Unchanged from `temporal_validation.py` (Task 3 does not modify it): a
fold's training rows are restricted by comparing dates directly, not by
list position after sorting, so two elections sharing a polling day (county
by-elections scheduled together, and the 2026 East/West Surrey elections
both on 7 May 2026) never train on each other.

### How structural zeros differ from missing data

A party's confirmed absence from a contest is never the same value as an
unresolved unknown. This layer inherits that distinction directly from the
target contract's `target_party_vote_share_status` (`not_defined_for_
multi_member_party_contest` vs a resolved numeric share) rather than
re-deriving it, and carries it through unchanged as `target_missingness_
type` in the coverage table.

### Why partial geographic crosswalks are excluded here

Cohort A requires `baseline_eligibility`'s primary status, which the
extractor only assigns from a single approved administrative predecessor,
never from a partial-coverage crosswalk weighting. This project's frozen
position on vote-share transfer across partial crosswalks (see `Supervisor
Requirement/` and this task's own instructions) is that it is not
attempted; this cohort mapping enforces that boundary by construction
rather than by convention.

### Why Reform UK and UKIP remain distinct

`standard_party_name` is never merged across the two labels anywhere in
this pipeline (verified directly by `test_ukip_and_reform_uk_are_never_
merged`); Reform UK's own prior-election history, where it exists, comes
only from Reform UK's own prior results, never from UKIP's.

## Live results (2026-07-22 release)

### Overall coverage and accuracy

| Model | Target | Eligible | Valid | Target-universe coverage | Eligibility-conditioned coverage | Own-covered MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `equal_share_reference_v1` | 1,603 | 1,139 | 1,139 | 71.1% | 100.0% | 14.56 |
| `party_historical_mean_reference_v1` | 1,603 | 1,139 | 750 | 46.8% | 65.9% | 10.42 |
| `previous_result_persistence_v1` | 1,603 | 775 | 775 | 48.3% | 100.0% | 9.50 |
| `ridge_fundamentals_v1` | 1,603 | 775 | 771 | 48.1% | 99.5% | 9.89 |

### By cohort (own-covered MAE; "n/a" = zero eligible rows in that cohort for that model)

| Model | Cohort A | Cohort B | Cohort C |
| --- | ---: | ---: | ---: |
| `equal_share_reference_v1` | 15.60 (775/775) | 8.73 (6/6) | 12.40 (358/358) |
| `party_historical_mean_reference_v1` | 10.43 (744/775) | 9.25 (6/6) | n/a (0/358) |
| `previous_result_persistence_v1` | 9.50 (775/775) | n/a | n/a |
| `ridge_fundamentals_v1` | 9.89 (771/775) | n/a | n/a |

### Common-sample MAE (740 contests every model predicted)

`previous_result_persistence_v1` 9.23, `ridge_fundamentals_v1` 9.66,
`party_historical_mean_reference_v1` 10.44, `equal_share_reference_v1`
15.60.

### Winner metrics

| Model | Available | Eligible areas | Predicted areas | Coverage | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: |
| `previous_result_persistence_v1` | yes | 177 | 169 | 95.5% | 80.5% |
| `party_historical_mean_reference_v1` | yes | 258 | 177 | 68.6% | 67.2% |
| `equal_share_reference_v1` | no | - | - | - | - |
| `ridge_fundamentals_v1` | no | - | - | - | - |

`equal_share_reference_v1` predicts an identical share for every party, so
it has no basis to name a winner. `ridge_fundamentals_v1` is a share
regression only in this task; no winner rule is defined for it.

## An unresolved methodological issue found by this task

`ridge_fundamentals_v1`'s eligibility-conditioned coverage is 99.5%, not
100%, even though its theoretical eligibility (`eligible_n3_ridge`) is
computed as Cohort A membership restricted to an evaluable temporal fold.
Investigation traced the 4 uncovered rows to one specific fold: the 2015-05-
07 Weybridge by-election, the second chronological election in the release.
Its training pool (358 rows, all from the 2013 study-start election) has
zero rows that pass the share cohort filter, because no 2013 row can itself
be Cohort A - 2013 has no predecessor of its own. `regularised_models.
evaluate_ridge_over_folds` correctly refuses to fit on an empty training
cohort and skips the fold entirely, so these 4 otherwise-eligible rows never
receive a ridge prediction.

This is a genuine, bootstrapping-style limitation of the fold-plus-cohort
design at the very start of the usable series, not a defect in either
`temporal_validation.py` or `regularised_models.py`, and this task does not
modify either module to work around it (per this task's own instruction not
to touch completed components without a demonstrated bug). It is recorded
here as an open question for whoever next revisits `regularised_models.py`:
whether an earliest-usable-fold special case is worth adding, and if so,
what it should predict with only zero cohort-eligible training rows
available.

## Reproduction

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_coverage_report.py
```

Writes `model_predictions_coverage.csv` (long format, one row per
party-contest x model), `model_comparison.csv` (one row per model) and
`coverage_report_audit.json` (join mismatches and the full per-cohort
summary) under `surrey-election-no-news-baseline/outputs/coverage_report/`,
deterministically and without a network request.
