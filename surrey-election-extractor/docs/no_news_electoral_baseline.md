# No-news electoral baseline release note

## Research role

The no-news baseline is the comparator required by the supervisor's central
question: whether pre-election news improves winning-party and party-vote-share
predictions beyond previous election results. Only information available before
the target poll may enter this baseline.

## Current division-level export

`outputs/no_news_electoral_baseline/no_news_electoral_baseline.json` contains
342 rows, one for every target division or ward:

- 204 rows have an approved historical predecessor;
- 138 rows visibly record that no predecessor is approved;
- 119 prior-turnout values come from official result pages;
- 85 prior-turnout values come from separately cited supplementary official
  evidence;
- all 204 eligible rows therefore have an analysis-ready prior turnout.

Each row retains predecessor identifiers, previous winning party, previous
winning-candidate share, previous electorate, previous turnout provenance,
historical source URL and permission sources.

## Leakage prohibition

The builder fails if any current-election outcome field enters the export.
Prohibited fields include current vote share, change in vote share, outcome,
elected status, official or derived rank, winning margin and analysis winning
margin. In particular, `change_in_vote_share` is never a baseline predictor
because it contains the current-election result.

## Party-contest modelling publication

`outputs/no_news_party_contests/` now publishes predictors and target-election
outcomes as separate JSON tables joined only by `party_contest_id`. This is a
structural leakage control rather than a naming convention.

- 1,619 party-contest rows are published;
- 1,155 are single-member party contests with a well-defined current target
  party share;
- 921 party-contest rows retain a governed lagged party share;
- 791 satisfy every condition for the primary single-member lagged-share
  experiment;
- 358 are 2013 rows with no in-scope predecessor;
- 6 otherwise single-member rows lack an approved unique exact-label prior
  party share;
- 464 are multi-member party contests retained for elected-party/seat analysis
  but excluded from the primary party-share estimand.

The master contains 1,037 candidate-level lagged shares whereas the
party-contest table contains 921. The reduction is intentional: candidates
from the same registered party in a 2026 two-member ward share one historical
party baseline and must not be counted as independent party observations.
Generic Independent labels remain candidate-specific.

For multi-member wards the release provides `target_best_candidate_vote_share`
as an explicitly named diagnostic and party election/seat targets. It does not
sum candidate shares or call that quantity a party vote share. Current vote
share, elected outcome, rank, margin and `change_in_vote_share` remain absent
from the feature table.

The model-input publication is now complete for its declared cohorts. Model
fitting, temporal validation and frozen prediction/metric release remain the
next no-news stage; this document does not claim that a baseline model has
already been trained.

This is a downstream modelling-publication gap, not a missing election-source
extraction value.

## Reproduction

From the repository root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_party_contests.py
```

Both outputs are deterministic over the committed audits and require no
network request.
