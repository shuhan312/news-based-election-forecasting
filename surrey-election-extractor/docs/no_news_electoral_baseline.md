# No-news electoral baseline release note

## Research role

The no-news baseline is the comparator required by the supervisor's central
question: whether pre-election news improves winning-party and party-vote-share
predictions beyond previous election results. Only information available before
the target poll may enter this baseline.

## Current division-level export

`outputs/no_news_electoral_baseline/no_news_electoral_baseline.json` contains
339 rows, one for every target division or ward:

- 201 rows have an approved historical predecessor;
- 138 rows visibly record that no predecessor is approved;
- 116 prior-turnout values come from official result pages;
- 85 prior-turnout values come from separately cited supplementary official
  evidence;
- all 201 eligible rows therefore have an analysis-ready prior turnout.

Each row retains predecessor identifiers, previous winning party, previous
winning-candidate share, previous electorate, previous turnout provenance,
historical source URL and permission sources.

## Leakage prohibition

The builder fails if any current-election outcome field enters the export.
Prohibited fields include current vote share, change in vote share, outcome,
elected status, official or derived rank, winning margin and analysis winning
margin. In particular, `change_in_vote_share` is never a baseline predictor
because it contains the current-election result.

## Remaining publication step

The master database contains 1,021 governed candidate-level
`previous_party_vote_share` values, but the current no-news JSON is
division-level and does not publish a candidate/party-keyed lagged-share table.
Consequently:

- the current division-level baseline is complete for its declared schema;
- the full no-news input for party-vote-share modelling is **not yet complete**;
- the next baseline task is to publish candidate/party rows keyed to target
  election, area and exact published party label, using only lagged fields;
- current vote share and change in vote share must remain excluded.

This is a downstream modelling-publication gap, not a missing election-source
extraction value.

## Reproduction

From the repository root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py
```

The output is deterministic over the committed audits and requires no network
request.
