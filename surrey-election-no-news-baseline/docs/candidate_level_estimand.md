# The candidate-level estimand and cohort

**Status:** adopted 28 July 2026. Supersedes nothing — the party-share
estimand is retained as a sensitivity check.

## The problem this solves

Every benchmark built before this change scores a **party** vote share, and
does so only on single-member contests, because a party vote share is not a
defined quantity under multi-member plurality: each elector casts up to
`seats` votes, so summing a party's candidate shares does not estimate that
party's support.

That restriction is methodologically right for the party estimand and wrong
for the project, because of one fact:

> The 7 May 2026 East and West Surrey elections were fought in two-member
> wards.

The supervisor's Stage 1 brief makes 7 May 2026 the **primary untouched
holdout**. Under the party cohort, that holdout contained **zero scorable
rows**. The project's headline comparison — does news improve on election
history — was therefore defined on a test set the model could not reach.

## The change

The brief already specifies the estimand that does not have this problem:

> "The primary target is `analysis_vote_share`. The model should predict vote
> share for every candidate in a contest."

A new candidate-level release is published alongside the party release:

| | party release | candidate release |
| --- | --- | --- |
| unit | election × area × party | election × area × candidate |
| target | party vote share | `analysis_vote_share` |
| rows published | 1,139 | 1,971 |
| rows in cohort | 775 | **1,971** |
| 7 May 2026 rows | **0** | **838** |
| 7 July 2026 rows | 0 | 4 |
| Reform UK rows | — | 175 (11 before 2026) |

Code: `election_extractor/no_news_candidate_contest.py` (release),
`no_news_baseline/candidate_cohort.py` (cohort, normalisation, allocation).

## Why the target is defined in a two-member ward

`analysis_vote_share` is candidate votes divided by **all votes cast in that
contest**. Verified against the published 2026 result pages: in the
two-member Ashtead Ward, twelve candidates' published shares sum to 101
against a total of 11,502 votes. The denominator is total votes cast, exactly
as in a single-member division. The quantity is observed, published and
internally consistent regardless of seat count.

The build enforces this rather than assuming it. Every contest is reconciled
to 100 within a derived tolerance of `2 + 0.5n` percentage points for `n`
candidates — at worst 0.5pp of rounding error per published whole-number
share, plus two points for the source's own rounding of the total. All 343
real contests in the current release pass (339 when this record was adopted;
the four by-elections integrated later also pass). A contest outside the band
stops the release instead of being silently renormalised.

## What is NOT claimed

A 25% candidate share in a two-member ward does not mean the same thing
politically as 25% in a single-member division: a party fielding two
candidates splits its support across two ballot lines, so its per-candidate
shares are mechanically lower.

Three construction choices keep this from becoming a hidden confound rather
than relying on a model to infer it:

1. `contest_structure`, `analysis_number_of_seats`,
   `candidate_count_in_contest` and `party_candidate_count_in_contest` are
   published as features, so the structural difference reaches the model as
   information.
2. `stratify_by_structure` requires metrics to be reported for single-member
   and multi-member contests separately as well as pooled. A pooled figure
   alone is uninterpretable: a model could look better merely by being scored
   on more multi-member contests.
3. The party release is retained as a sensitivity check on the single-member
   subset, where the two estimands provably coincide. If a substantive
   conclusion holds under one estimand and not the other, that is a finding to
   report, not a discrepancy to resolve by picking the more convenient one.

## The eligibility change

The party release folds two different questions into one field:

- is this row a valid prediction target?
- does an approved lagged predictor exist for it?

Requiring **both** is what removed 2026 from the cohort, because most 2026
wards have changed boundaries and therefore no approved predecessor share.

The candidate release separates them:

| field | question answered |
| --- | --- |
| `candidate_baseline_eligibility` | can this row be a prediction target? |
| `historical_predictor_availability` | why is a lagged predictor present or absent? |

Observed availability on the real release:

| `historical_predictor_availability` | rows |
| --- | ---: |
| `approved_previous_party_share` | 1,021 |
| `no_approved_area_reference` | 932 |
| `approved_area_no_previous_party_share` | 18 |

This follows the brief's own instructions — "Create missingness indicators
where they may be useful" and "Unknown values must remain unknown" — and it
matters beyond sample size. Complete-case deletion here would not merely
shrink the cohort; it would **bias** it, because the wards lacking an approved
predecessor are exactly the reorganised ones, and local-government
reorganisation is not independent of political change.

## Contest normalisation, ranking and seats

The target is compositional, so an unconstrained per-row regression will not
produce a set of predictions summing to 100. `normalise_within_contest`
rescales within each `election_id + division_id` contest, as the brief
requires. Both values are kept: the raw model output (what
feature-importance and residual diagnostics trace back to) and the normalised
value (what may be compared with the observed share). Negative predictions
are clipped to zero before rescaling, because a negative share is outside the
target's support and would otherwise invert another candidate's contribution.

`allocate_contest` then ranks candidates and elects the top `seats`. This is
where the multi-member holdout is actually served: the brief's instruction to
"use the known pre-election number of seats to select the predicted winner or
winners" generalises the single-member winner rule to two-member wards with no
new assumption. Seat count is known once nominations close, so using it leaks
nothing.

Ties are made explicit rather than resolved by luck. A deterministic
tie-break on a stable identifier keeps reruns reproducible, but any tied
candidate is flagged, and a tie straddling the seat cutoff labels the whole
contest `allocated_with_tie_at_cutoff` — the elected set is then an artefact
of the tie-break, and seat-accuracy metrics should be able to say how often
that happened.

## Reform UK sample, by fold

`is_reform_uk` and `is_ukip` are two independent indicators. No row may set
both; the release build fails if one ever does.

Reform UK rows in the cohort: **175 total, 11 before 2026** (2021: 6; 2025
by-elections: 5) against 163 on 7 May 2026 and 1 at the July Haslemere
by-election.

Consequence for the split, from
`scripts/build_candidate_cohort_report.py`:

| split | train | validation | test |
| --- | ---: | ---: | ---: |
| supervisor's email (train 2013–2019, validate 2021, test 2026) | **0** | 6 | 169 |
| Reform-aware (train to end 2021, validate 2025 by-elections, test 2026) | 6 | 5 | 164 |

The split as written in the supervisor's email trains on **zero** Reform UK
observations. That is not an implementation detail: under it, no
Reform-specific coefficient or interaction can be estimated at all, and any
Reform result on the holdout would come entirely from the pooled all-party
model. Both splits are emitted so the comparison is explicit; the choice is
the supervisor's.

## Reproduction

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/build_candidate_cohort_report.py
```

## Reversal path

The candidate release is additive. Nothing in the party release, the
persistence benchmark, the naive benchmarks or the fundamentals table was
edited. Deleting `no_news_candidate_contest.py`, `candidate_cohort.py` and
their tests returns the package to its previous state exactly.
