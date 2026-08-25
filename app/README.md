# `app/` — the news-layer Streamlit interface

A Layer 8 consumer: a thin, **read-only** viewing layer over the artefacts the
pipeline has already produced. It does not process, fit or re-drive anything —
the news layer ran through the auditable CLI pipeline and its outputs are frozen,
so this app only displays them. Re-driving processing here would either duplicate
the CLI or, worse, invite reading an outcome the design keeps blinded.

## The three pages

`news_app.py` presents:

- **Status** — what has run and which frozen artefacts are loaded (the Stage 1
  bundle, the feature table, the corpus release), each shown with its version and
  `sha256` so the app can be trusted to be reading the committed evidence.
- **Results** — the news layer's confirmatory results, carrying the statistical
  interpretation warning the design requires on any results surface.
- **Scenarios** — how the fitted model responds to a hypothetical news story; the
  scenario page re-verifies the inputs it uses.

## What it reads (read-only)

| Artefact | From |
| --- | --- |
| Stage 1 model bundle | `surrey-election-no-news-baseline/outputs/model_bundle_v1/` |
| News feature table | `news_features/news_feature_table_v2.csv` |
| Corpus release | `news_collection/canonical_corpus_release_v2.json` |
| Blinded-prediction manifest | the committed `sha256_manifest.json` beside the predictions |

Everything it shows already exists as a frozen, hash-pinned artefact; the app adds
a view, never a new number.

## Running

From the repository root, with the project `.venv` active:

```bash
streamlit run app/news_app.py
```

This is the **news-layer** app. The Stage 1 baseline has its own six-page
application (`surrey-election-no-news-baseline/app/`) and the extractor has its own
(`surrey-election-extractor/app.py`); both are separate and untouched by this one.
See [`../REPO_MAP.md`](../REPO_MAP.md) for how Layer 8 consumers sit on top of the
frozen report pack.
