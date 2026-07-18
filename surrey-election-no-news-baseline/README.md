# Surrey Election No-News Baseline

This directory contains the modelling and evaluation layer for the supervisor's
central comparator: what can be predicted from previous election results before
adding any news features.

It is a sibling of `surrey-election-extractor`, not a separate Git repository.
The two directories have different responsibilities:

- `surrey-election-extractor` owns official-source extraction, provenance,
  derived/analysis governance and publication of model-input data contracts;
- `surrey-election-no-news-baseline` owns predictions, metrics, cohort
  evaluation and later learned no-news models.

The modelling layer never edits official election data and does not import the
extractor's internal Python modules. It reads two generated JSON contracts:

```text
surrey-election-extractor/outputs/no_news_party_contests/
├── no_news_party_contest_features.json
└── no_news_party_contest_targets.json
```

Separating features and targets is a structural target-leakage control.

## Current benchmark

`previous_result_persistence_v1` applies two parameter-free rules:

```text
predicted party share = approved previous exact-label party share
predicted elected party = previous winner, when uniquely present on the current ballot
```

It evaluates 775 party-share rows across 177 approved single-member areas. A
winner prediction is available for 169 areas; eight remain explicitly unscored
where political identity cannot be transferred safely.

See [`docs/persistence_benchmark.md`](docs/persistence_benchmark.md) for the
methods, headline results and interpretation boundaries.

## Reproduction

Run from the IRP repository root.

First regenerate the extractor-owned input contract if required:

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_party_contests.py
```

Then run the benchmark:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_persistence_benchmark.py
```

Run its independent tests with:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/pytest -q \
  surrey-election-no-news-baseline/tests
```

Generated predictions and metrics are written under
`surrey-election-no-news-baseline/outputs/` and are intentionally excluded from
Git. Code, tests, data-contract documentation and research decisions remain
version controlled.

## Planned internal structure

```text
no_news_baseline/
├── persistence_benchmark.py       # completed parameter-free benchmark
├── naive_benchmarks.py            # next: non-geographic reference rules
├── temporal_validation.py         # future rolling-origin evaluation
├── regularised_models.py          # future interpretable learned baselines
└── uncertainty.py                 # future clustered/bootstrap intervals
```

News collection and news-aware models should remain outside this directory
until the no-news comparison cohort, metrics and prediction release are frozen.
