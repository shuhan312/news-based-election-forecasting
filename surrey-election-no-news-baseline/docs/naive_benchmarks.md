# Non-geographic naive reference rules

## Research question and role

`persistence_benchmark.md` shows that carrying forward each area's own
previous party result predicts the current result with reasonable accuracy.
On its own, that result cannot separate two different explanations:

1. the model works because it knows something genuinely local about that
   specific division (the explanation the supervisor's "no news vs news"
   comparison is designed around), or
2. the model works mainly because it knows roughly how well that party does
   across Surrey in general, and the choice of division contributes little.

This document evaluates two rules that deliberately discard area identity, so
that any advantage `persistence_benchmark` shows over them can be attributed
to genuine local information rather than to party identity alone. The design
follows the "persistence vs. climatology" contrast used throughout forecast
verification, and mirrors the comparator hierarchy used in Hanretty (2021,
Section 5.4, comparison against a uniform-swing method) and Stoetzer,
Neunhoeffer, Gschwend, Munzert & Sternberg (2025, Sections 4-5.1,
fundamentals-only comparator against polls-only and combined models).

## The two rules

Both rules have no fitted parameters and obey the same leakage rules declared
in `electoral_fundamentals_schema.LEAKAGE_RULES`; neither aggregates
current-election results from other areas.

- **`equal_share_reference_v1`**: predicted share = 100 / (number of
  standardised parties on the current single-member ballot). Uses no
  historical data of any kind. This is the uninformed floor every other
  benchmark, naive or fitted, must beat.
- **`party_historical_mean_reference_v1`** ("climatology"): predicted share =
  mean realised vote share for that party across every Surrey election
  strictly before the target election date, pooled across areas. Hanretty's
  uniform-swing comparator plays an equivalent role but needs contemporaneous
  national polling data that does not exist for Surrey county elections; a
  historical cross-area mean is the closest no-news equivalent this project's
  own data can support. A party with no qualifying prior contest (most
  notably a new entrant) is left unscored rather than assigned an invented
  value.

## Common support with the persistence benchmark

Both rules are eligible on more rows than `persistence_benchmark`'s own
cohort (`docs/persistence_benchmark.md`, "Interpretation boundary": a model
does not show added value merely by scoring more rows). Every prediction is
tagged with whether it falls inside `persistence_benchmark`'s share cohort
(775 rows) and winner cohort (781 rows) respectively, and the reported
`common_support_with_persistence_benchmark` metrics restrict the share half
and the winner half of the comparison separately to those exact row counts,
so the headline numbers below are read on the same population
`persistence_benchmark.md` reports.

An earlier version of this comparison pooled the share and winner cohort
tags with a single "or" before scoring, which let extra winner-cohort-only
rows leak into the share comparison (781 rows instead of 775). This was
caught by inspecting the live output rather than trusting the code in the
abstract, fixed in `naive_benchmarks._metrics_block`, and is now guarded by
`test_common_support_share_metrics_do_not_leak_in_winner_only_rows`.

## Results (live release, common support with persistence_benchmark)

| Benchmark | Share rows | MAE (pp) | RMSE (pp) | Median AE (pp) | Winner rows scored | Area winner accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| `previous_result_persistence_v1` (existing) | 775 | 9.50 | 14.05 | 6.00 | 169 / 177 areas | 80.5% |
| `party_historical_mean_reference_v1` (new) | 744 | 10.43 | 13.75 | 7.42 | 781 / 781 (177 areas) | 67.2% |
| `equal_share_reference_v1` (new) | 775 | 15.60 | 18.44 | 14.29 | not applicable | not applicable |

Persistence figures are taken from `docs/persistence_benchmark.md`. The
climatology share-row count (744) is slightly below the 775-row persistence
share cohort: 31 of those 775 rows have an approved area-level lagged share
recorded by the extractor's own historical-reference pipeline but no
qualifying observation in this module's own cross-area target pool (for
example, because the immediate predecessor contest itself was multi-member or
had more than one candidate for the party, so it never produced a resolved
single-member `target_party_vote_share`). This is a genuine evidence-boundary
difference between two independently constructed evidence pathways, not an
error; it is reported rather than reconciled away.

## Interpretation

**Party identity does most of the work that area identity is often credited
with, for vote share.** Moving from no history at all (15.60) to
area-specific history (9.50) closes most of the error gap, but moving from
area-specific history (9.50) to only knowing the party's general Surrey-wide
level (10.43) gives up under one percentage point of MAE. The bulk of
`persistence_benchmark`'s accuracy over the uninformed floor is explained by
knowing which party is which, not by knowing which division is which.

**Area identity matters much more for calling the winner than for calling the
share.** The area-winner-accuracy gap between persistence (80.5%) and
climatology (67.2%) is 13.3 percentage points - far larger, proportionally,
than the 0.93-point share MAE gap. Seats are frequently decided by margins
narrow enough that area-specific information becomes decisive even where it
barely moves the share estimate.

**Climatology's blind spot is exactly where the supervisor's news question
lives.** 389 of the 750 full-cohort party-contest rows (52%) have no
qualifying prior Surrey result at all and are left honestly unscored rather
than guessed at zero. These are disproportionately new-entrant contests -
early Reform UK candidacies most notably - which is precisely the scenario
`Supervisor Requirement/Supervisor requirement.txt` asks whether news
coverage "can identify the emergence of a newer party before it has a
substantial historical voting record." A pure-history model structurally
cannot address this question; it is a natural, evidence-based motivation for
the news-aware models planned later in this project, not a defect to fix
inside this benchmark.

## Reproduction

From the repository root:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_naive_benchmarks.py
```

Deterministically regenerates row-level predictions, both full-cohort and
common-support metrics, and a coverage audit for each rule, without a network
request.
