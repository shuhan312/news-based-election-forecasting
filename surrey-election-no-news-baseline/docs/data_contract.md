# Extractor-to-baseline data contract

## Ownership boundary

The extractor publishes two JSON objects, each with a top-level `rows` list.
This modelling directory treats those files as read-only inputs and joins them
only through the unique `party_contest_id`.

## Feature contract

`no_news_party_contest_features.json` contains only information available
before the target election. Important fields include:

- election, area and party identifiers;
- contest structure and approved historical-reference status;
- previous party vote share, winner, turnout and electorate;
- prior contest, first-appearance and evidence-status fields;
- source and permission provenance.

Current votes, current vote share, elected outcome, rank, margin and
`change_in_vote_share` are prohibited from this table.

## Target contract

`no_news_party_contest_targets.json` contains current-election outcomes:

- single-member party vote share where scientifically defined;
- party elected status and seats won;
- explicitly labelled best-candidate share for multi-member diagnostics;
- current official source URLs.

The persistence benchmark fails if feature and target identifiers are not
unique and identical. It does not silently inner-join away unmatched records.

## Versioning rule

Any future schema change must be implemented and tested in the extractor first.
The modelling layer should then update its contract validation in a separate,
well-described commit. Generated JSON is not manually edited.

## NULL handling for model inputs

The published fundamentals table keeps raw NULLs. The separate model-input
contract assigns each nullable predictor a missing flag, an applicability flag
and an audit reason: `study_start`, `party_did_not_contest`, `not_applicable`,
`changed_boundary` or `insufficient_evidence`.

The 2013 rows remain available to supply history for 2017 but are not eligible
prediction targets because no earlier Surrey election is included. All 2026
rows remain eligible; complete-case deletion is prohibited because it would
systematically remove changed-boundary wards.

Any required numeric or boolean imputation is fitted separately inside each
training fold. Validation and test rows are transformed only after those
training-fold values have been fixed. Missing and applicability indicators are
retained, so an unknown value is never interpreted as an observed zero or
False. No imputed value is written back to the fundamentals table.
