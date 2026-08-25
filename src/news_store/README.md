# `src/news_store/` — the article store

Cleaning layer support: the store that holds the collected news articles during
cleaning and deduplication. Small and deliberately so — two modules and a schema.

| Module | Role |
| --- | --- |
| `schema.py` | The SQLite schema and the one structural idea it is built around |
| `store.py` | The store's public interface (how the pipeline reads and writes articles) |

The store is a local working artefact: the article records themselves live under
`data/raw/news/` and are not committed (copyright and the IRP large-file rule).
Code here is versioned so the store can be rebuilt from the raw records. See
`REPO_MAP.md` for how collection, cleaning and labelling use it.
