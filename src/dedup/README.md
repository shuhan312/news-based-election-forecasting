# `src/dedup/` — deduplication (Layer 2, Phase 5)

Cleaning layer, second half: identify duplicate, syndicated and updated copies of
the same article and select one canonical version, so the corpus counts each
piece of news once. Each Phase 5 step is a **pure-logic module** plus a
**`build_` runner** that applies it over the frozen articles.

## The Phase 5 steps

```text
1  exact_duplicates    exact content-duplicate detection
2  url_canonical       canonical URL resolution and URL-group resolution
3  near_duplicates     near-duplicate detection
4  syndication         syndicated-copy identification
5  versioning          updated-article and version linking, temporal availability
6  cluster_validation  duplicate-cluster validation
7  canonical_selection canonical article selection (one kept per cluster)
8  mapping_layer       consolidate steps 1–7 and freeze the duplicate mapping
```

## Layout

| Module | Role |
| --- | --- |
| `exact_duplicates.py`, `url_canonical.py`, `near_duplicates.py`, `syndication.py`, `versioning.py`, `cluster_validation.py`, `canonical_selection.py`, `mapping_layer.py` | The pure-logic step implementations |
| `build_exact_duplicates.py` … `build_mapping_layer.py` | The per-step runners |

## Running and outputs

Run the `build_` steps in order (from the repository root), e.g.:

```bash
python3 -m src.dedup.build_exact_duplicates
python3 -m src.dedup.build_url_resolution
python3 -m src.dedup.build_near_duplicates
python3 -m src.dedup.build_syndication
python3 -m src.dedup.build_versioning
python3 -m src.dedup.build_cluster_validation
python3 -m src.dedup.build_canonical_selection
python3 -m src.dedup.build_mapping_layer
```

The stage is **deterministic** — it reads the frozen cleaned articles and
produces the same duplicate mapping on every run. Outputs (the version families,
the canonical article mapping, review queues and the frozen
`canonical_corpus_release_*.json`) land in the repository-root `news_collection/`
directory; see its README. Step 8 freezes the mapping that downstream layers use
to work from one canonical copy per news item.

## Discipline

A duplicate is never deleted — it is mapped to its canonical copy, so the
grouping is auditable and reversible. Near-duplicate and syndication decisions
are validated (step 6) before the mapping is frozen (step 8). See `REPO_MAP.md`.
