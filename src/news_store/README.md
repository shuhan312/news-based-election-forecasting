# `src/news_store/` — the article store (Layer 2 support)

Cleaning layer support: the store that holds the collected news articles during
cleaning and deduplication. Small and deliberately so — two modules and a schema.

| Module | Role |
| --- | --- |
| `schema.py` | The SQLite schema and the one structural idea it is built around |
| `store.py` | The store's public interface (how the pipeline reads and writes articles) |

## Running and verification

This package has no standalone command. It is a library used by the Layer 2
normalisation and deduplication builders; do not run `schema.py` or `store.py`
directly. Verify its deterministic storage and provenance rules with:

```bash
PYTHONPATH=src python -m pytest tests/test_news_store.py
```

The store is a local working artefact: the article records themselves live under
`data/raw/news/` and are not committed (copyright and the IRP large-file rule).
Code here is versioned so the store can be rebuilt from the raw records. See
`REPO_MAP.md` for how collection, cleaning and labelling use it.
