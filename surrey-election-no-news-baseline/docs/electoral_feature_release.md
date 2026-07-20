# Electoral fundamentals feature release

This record freezes the feature-engineering release used before modelling or
adding news variables. The generated CSV files remain outside Git because they
are reproducible from the extractor contracts and can be large.

## Frozen release

- Release date: 20 July 2026
- Input data version: `330219b650a3cd31`
- Method version: `electoral-fundamentals-v4-independent-null-semantics`
- Release version: `cbbb96938bf75f27`
- Unit of analysis: one `election × area × standardised party` row
- Rows and unique keys: 1,592
- Predictors: 16
- Dictionary fields: 47
- Full-suite result: 75 tests passed

The release contains 357 study-start rows from 2013. They can supply historical
evidence but are not prediction targets because no earlier Surrey election is
in scope. All 466 rows dated in 2026 remain eligible for later evaluation;
changed-boundary NULLs are not removed by complete-case filtering.

## Published artifacts

Running the release commands creates:

- `electoral_fundamentals_features.csv` — predictors, provenance and separately
  named evaluation outcomes;
- `electoral_fundamentals_predictors_only.csv` — identifiers and the 16
  pre-election predictors only;
- `electoral_feature_dictionary.csv` — definitions, sources, temporal
  availability and model-use rules for all 47 released fields;
- `electoral_fundamentals_data_quality.md` — input hashes, coverage and release
  identity;
- `electoral_fundamentals_model_input_contract.csv` — raw predictors with
  missing and applicability indicators, before fold-specific imputation;
- `electoral_fundamentals_null_semantics.md` — counts for each field and NULL
  reason.

## Remaining NULL boundaries

NULL does not have one common meaning in this release. The model-input contract
distinguishes study start, party did not contest, not applicable, changed
boundary and insufficient evidence. In particular:

- generic Independent and blank-label records do not inherit party history;
- a party that did not contest may have an observed zero share but has no rank;
- positive previous vote shares are not redistributed across changed 2026
  boundaries without suitable electorate weights;
- UKIP history remains separate from Reform UK's own previous vote share;
- Unknown incumbency is not treated as an observed `False`.

These are evidence boundaries rather than extraction failures. Missing and
applicability indicators are retained, and any imputation must be fitted using
the training fold only.

## Reproduction and QA

Run from `surrey-election-no-news-baseline`:

```bash
../.venv/bin/python scripts/build_electoral_fundamentals_release.py
../.venv/bin/python scripts/build_model_input_contract.py
../.venv/bin/python -m pytest -q
```

The verified release has identical row keys across the full table,
predictors-only table and model-input contract. The predictor and model-input
files contain no `evaluation_` columns, all released dates use ISO
`YYYY-MM-DD`, and all 2026 rows are retained.
