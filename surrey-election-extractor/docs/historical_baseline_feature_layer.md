# Historical baseline feature layer

This component prepares election-history-only information for the supervisor's
comparison between a no-news model and later news-aware models. It is read-only
over official extraction, party standardisation and approved historical
permissions; it does not collect news, train a model or predict an outcome.

The master contains 205 approved historical area references and 1,042
candidate-level exact-label previous-party shares. An `accepted_direct` GIS
relationship is not sufficient by itself: the relation must also be approved
by the official boundary-evidence audit. Partial, non-comparable, review-pending
and unapproved relationships block electoral transfer. Votes are never
redistributed and Reform UK is never merged with UKIP.

The current no-news publication has 343 division-level rows. Of these, 205 have
an approved predecessor and 138 do not. Previous turnout is available for all
205 eligible rows: 120 from official result pages and 85 from separately cited
supplementary official evidence. Runtime checks prohibit current vote share,
outcome, rank, margin and change-in-share fields.

This division-level publication is leakage-safe but is not itself the complete
party/candidate modelling table: the 1,042 candidate-level previous-party-share
values are published through the separately keyed candidate-contest release
(`outputs/no_news_candidate_contests/`, built by
`scripts/generate_no_news_candidate_contests.py`), which the Stage 1 baseline
consumes. See [`no_news_electoral_baseline.md`](no_news_electoral_baseline.md).

## Reproduction

From the repository root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_historical_baseline_features.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py
```
