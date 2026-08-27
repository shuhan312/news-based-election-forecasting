# No-news electoral baseline release note

## Research role

The no-news baseline is the comparator required by the supervisor's central
question: whether pre-election news improves winning-party and party-vote-share
predictions beyond previous election results. Only information available before
the target poll may enter this baseline.

## Current division-level export

`outputs/no_news_electoral_baseline/no_news_electoral_baseline.json` contains
343 rows, one for every target division or ward:

- 205 rows have an approved historical predecessor;
- 138 rows visibly record that no predecessor is approved;
- 120 prior-turnout values come from official result pages;
- 85 prior-turnout values come from separately cited supplementary official
  evidence;
- all 205 eligible rows therefore have an analysis-ready prior turnout.

Each row retains predecessor identifiers, previous winning party, previous
winning-candidate share, previous electorate, previous turnout provenance,
historical source URL and permission sources.

## Leakage prohibition

The builder fails if any current-election outcome field enters the export.
Prohibited fields include current vote share, change in vote share, outcome,
elected status, official or derived rank, winning margin and analysis winning
margin. In particular, `change_in_vote_share` is never a baseline predictor
because it contains the current-election result.

## Candidate-contest modelling publication

The modelling release that accompanies this baseline is the candidate-contest
publication, `outputs/no_news_candidate_contests/` (1,992 rows, one per
election, area and candidate), which is the final Stage 1 input contract.
Predictors and target-election outcomes are published as separate JSON tables
joined only by `candidate_contest_id` — a structural leakage control rather
than a naming convention. The earlier party-contest publication was a
development route and has been retired; its rationale remains in Git history.

## Reproduction

From the repository root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

Both outputs are deterministic over the committed audits and require no
network request.
