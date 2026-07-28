# Change-in-vote-share outcome policy

## Purpose and modelling role

The supervisor requires both `previous_party_vote_share` and
`change_in_vote_share`. The latter is published as a **post-election outcome and
diagnostic field**, calculated in percentage points as:

`current analysis_vote_share − approved previous_party_vote_share`

It must not be used as an input to a model predicting the same election. It
contains the current election's vote-share outcome and would therefore create
target leakage. The no-news baseline enforces this boundary with an explicit
runtime deny list.

## Eligibility

A candidate row receives a value only when:

1. the historical-reference layer has approved a directly comparable lineage;
2. the exact published party label is valid and unique under that audit;
3. the approved prior single-member candidate/party share is numeric;
4. the current contest is also single-member, using official Seats first and
   separately cited statutory Seats only when the official page omits it; and
5. the current analysis vote share is numeric and retains its provenance.

No fuzzy party matching, UKIP/Reform merging, candidate identity assumption,
party-total reconstruction or geographic vote redistribution is performed.

## Multi-member boundary

The 2026 wards are two-member contests. A candidate share in that ballot is not
the same estimand as a party share in a prior single-member division. Even where
a limited historical reference is approved, subtracting those values would
mislabel a candidate-level difference as party swing. All 246 otherwise
reference-supported 2026 candidate rows therefore remain `NULL` for this field.

## Current release

- 796/1,992 candidate rows have a governed outcome-diagnostic change.
- 246 rows are blocked because the current contest is multi-member.
- 950 rows lack an approved exact-label previous share.
- 0 values are permitted in the no-news baseline.

The 775 available rows comprise 372 records from 2017, 331 from 2021 and 72
from approved single-member by-elections. Official source fields remain
unchanged.
