# Context Aggregation Audit

Phase 7, Step 5. Version `context-aggregation-v1.0-2026-07-27`.

## Inputs used (all read-only)

Article-level feature layer (207 rows, Step 4), Phase 5 canonical
mapping (canonical-only gate re-asserted), Step 2 window
assignments and Step 3 scope labels (already embedded in the
article layer), frozen taxonomy v1.3 and 16-frame enum, freeze
manifest (hash re-verified before building).

## Aggregation units and row counts

**544 aggregate rows x 239 columns**: 129 individual-window rows
(partition - counts add and reconcile exactly with the article
layer, tested) and 415 cumulative-window rows (nested - counts
overlap, monotonicity tested, never summed). Scope split:
surrey_wide_local 378, national_political 71, mixed 69,
ward_specific_local 18, uncertain 6, regional 2. The
surrey-wide/ward dominance in row count comes from the 2026
candidate-guide article fanning legitimately across its 43
validated ward targets; national aggregates stay election-wide
(tested - no national row carries a ward target).

## Coverage statistics

Largest group: ESWS-2026 x election-wide x Conservative x
cumulative previous_180_days x national scope, n = 8 articles.
Most groups are small at pilot scale (median 1-2 articles) - the
machinery is validated here; analytical use begins at full-corpus
scale. 203 groups have a positive stance denominator; 341 have
stance_denom = 0 (typically no-focal-party or quarantined-layer
groups) and their proportions are None, not zero.

## Sentiment and stance aggregates

Sentiment baseline = stance distribution (no independent sentiment
layer exists in the frozen contract; mean_sentiment_score recorded
as not_extracted rather than derived). Stance separation verified
by reconciliation: a group's negative count equals the article
layer filtered to exactly that focal party.

## Issue, frame, attribution and consequence aggregates

28 frozen issue codes x {primary, any, proportion, continuing}
per group (any >= primary and single-primary bounds tested); 16
frozen frame categories with multi-frame and unclear counts; blame/
credit received vs assigned kept directionally separate with a
descriptive (possibly negative) net count; eight consequence
signals plus switching endpoint counts serialised per party ID.

## Unresolved and no-news groups

The five-state discipline survives aggregation: group denominators
count only observed layers, so quarantined and not-applicable rows
never inflate a denominator; 341 zero-denominator group-signals are
reported as None. No missing-news indicators were created (next
step's boundary), and nothing was imputed.

## Validation findings

All checks pass: unique keys; canonical-only contributions (each
article once per group, asserted at build); exact individual-window
reconciliation; proportions in [0,1] over documented denominators;
counts integral (only the descriptive net count may be negative);
frozen-vocabulary-only issue and frame columns; Reform/UKIP
separation; full provenance (contributions file row-for-row, list
lengths equal cov_n_articles); byte-identical rebuild; frozen layer
and article layer untouched.

## Test results

10 new tests in `tests/test_context_aggregation.py` - 10 passed.
Full repository suite: **553 passed, 0 failed**.
