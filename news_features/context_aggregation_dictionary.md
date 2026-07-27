# Context Aggregation Dictionary

Version `context-aggregation-v1.0-2026-07-27`. Files:
`context_aggregated_features.parquet` + `.csv` (544 rows x 239
columns at pilot scale) + `context_aggregation_contributions.json`
(row-to-article provenance).

## Aggregation keys (row identity, unique, tested)

`election_id | geographic_target_id | focal_party_id | window_type
| window | scope_classification`

* `window_type=individual`: the six disjoint pre-election windows.
  Articles partition across them - counts ADD across windows and
  reconcile exactly with the article layer (tested).
* `window_type=cumulative`: the six nested windows. An article
  contributes to every window it falls in - counts OVERLAP and
  **must never be summed across cumulative windows** (nesting
  monotonicity is tested instead).
* `scope_classification` keeps local / national / regional / mixed
  / uncertain aggregates fully separate; no row pools scopes, and
  national rows sit only at election-wide targets (tested).
* `focal_party_id="(no_focal_party)"` rows aggregate the non-party
  context of articles without a resolved Surrey party link.

## Denominator rule (applies to every proportion)

Each `*_prop` divides its `*_n` by the named `*_denom` beside it.
A proportion is **None when its denominator is 0** ("no eligible
articles observed for this signal group") and **0.0 only when the
denominator is positive** ("news observed, signal absent"). The
denominators are:

| denom | eligible rows |
|---|---|
| cov_n_articles | all rows of the group |
| stance_denom | stance group extracted or confirmed_absent |
| framing_denom | framing extracted |
| attribution_denom | attribution extracted |
| issues_denom | issues extracted |
| consequence_denom | consequence extracted or confirmed_absent |
| reform_denom | Reform focal rows with the block observed |

## Feature groups

**1. Coverage** (`cov_*`): unique canonical article count (the
universal denominator), publication and source-arm counts,
full-text / review-flagged / unresolved-alignment / result-flagged
counts, total party and candidate mentions. Modelling use: exposure
denominators and data-quality controls.

**2. Sentiment baseline** (`positive/neutral/negative/mixed_
stance_n/_prop`, `mean_sentiment_score`): the frozen contract has
no independent sentiment layer and no adopted label-to-number
mapping, so the baseline IS the stance distribution and
`mean_sentiment_score` is honestly None (`not_extracted`) - never
derived from labels. Modelling use: the simple baseline richer
stance features must beat.

**3. Stance** (same bins plus `praise/criticism_indicator_n/_prop`,
`competence_positive/negative_n/_prop`, `integrity_*`): focal-party
rows only; another party's stance can never enter (reconciliation
tested). Modelling use: tone-of-coverage features per party cell.

**4. Framing** (`frame_<cat>_n/_prop` x16 frozen categories,
`frame_multi_n`, `frame_unclear_or_missing_n`): distribution over
the approved enum only. Modelling use: narrative-mix features.

**5. Attribution** (`blame/credit_received_n/_prop`,
`blame/credit_assigned_n`, `responsibility_unclear_n`,
`net_credit_minus_blame_n`): received = focal as target, assigned =
focal as source, never merged. The net count is descriptive; it may
be negative and **must not be read causally**.

**6. Issues** (`issue_<code>_primary_n / _any_n / _any_prop /
_continuing_n` x28 frozen codes): one primary per article (primary
sums bounded by issues_denom, tested), multi-hot any-issue
membership (any >= primary, tested), continuing-story counts per
issue. Modelling use: agenda-composition features.

**7. Electoral-consequence signals** (`consq_<signal>_n/_prop` for
benefit / damage / mixed-unclear / growth / decline / credible-
challenger / anti-incumbent / voter-switching;
`switch_from_counts` / `switch_to_counts` as sorted "party_id:n"
strings): extracted news signals, not predictions.

**8. Reform UK block** (`reform_*_n`, `reform_credible_challenger_
prop`, `reform_org_strength_reported_n/_strong_n`,
`reform_credibility/momentum_mean/_median`, `reform_agg_status`):
aggregated only on Reform UK focal rows; every other party
(including UK Independence Party) carries
`reform_agg_status=not_applicable` with None values (tested).

## Provenance

`context_aggregation_contributions.json` maps every aggregate row
key to the sorted canonical article IDs behind it; list length
equals `cov_n_articles` (tested). Version stamps
(aggregation/features/frozen-dataset) ride on every row.
