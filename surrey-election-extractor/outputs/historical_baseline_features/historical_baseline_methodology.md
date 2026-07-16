# Historical Baseline Feature Layer Methodology

## Purpose

This layer creates the election-history-only baseline needed for a later test of whether news context adds predictive information beyond past election information. It does not collect news, train a model or make a prediction.

## Geographic rule

Only a single reviewed `accepted_direct` historical-to-2026 relationship with
`previous_winner_allowed=true` can expose a prior-event reference. This explicit
permission is separate from the GIS decision: an accepted spatial match alone
does not authorise election-history transfer. Partial crosswalk, not-comparable,
requires-review and unpermitted direct relationships are retained in the
readiness dataset as evidence, but cannot create prior-winner, prior-vote-share,
turnout-comparison, candidate-transfer or incumbency features.

## Source and missing-value rule

Official published values are copied unchanged. Same-event counts are marked `deterministically_derived`. Reviewed exact party mappings are marked `manually_confirmed` in their source records. Unsupported values remain `NULL` with `unavailable` provenance; they are never zero-filled.

## Party and candidate safeguards

Party presence uses exact original published party labels in an accepted direct lineage. UK Independence Party and Reform UK remain separate. Candidate history is infrastructure only: an identical candidate name is not evidence of a shared person, so candidate continuity, incumbency and predecessor fields remain unresolved.
