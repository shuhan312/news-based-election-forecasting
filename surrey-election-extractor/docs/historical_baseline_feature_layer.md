# Historical baseline feature layer

This component prepares election-history-only information for the supervisor's
comparison between a no-news model and later news-aware models. It is read-only
over official extraction, party standardisation and approved historical
permissions; it does not collect news, train a model or predict an outcome.

The master contains 201 approved historical area references and 1,021
candidate-level exact-label previous-party shares. An `accepted_direct` GIS
relationship is not sufficient by itself: the relation must also be approved
by the official boundary-evidence audit. Partial, non-comparable, review-pending
and unapproved relationships block electoral transfer. Votes are never
redistributed and Reform UK is never merged with UKIP.

The current no-news publication has 339 division-level rows. Of these, 201 have
an approved predecessor and 138 do not. Previous turnout is available for all
201 eligible rows: 116 from official result pages and 85 from separately cited
supplementary official evidence. Runtime checks prohibit current vote share,
outcome, rank, margin and change-in-share fields.

This division-level publication is leakage-safe but is not yet the complete
party/candidate modelling table: the 1,021 candidate-level previous-party-share
values still need a separately keyed baseline export. See
[`no_news_electoral_baseline.md`](no_news_electoral_baseline.md).

## Reproduction

From the repository root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_historical_baseline_features.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py
```
