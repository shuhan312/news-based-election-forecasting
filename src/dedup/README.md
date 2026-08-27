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

## Complete file guide

One pure-logic module and one `build_` runner per step; `tests/test_<step>.py`
covers each logic module.

| Step | Logic module | Runner | What the runner writes |
| --- | --- | --- | --- |
| 1 | `exact_duplicates.py` | `build_exact_duplicates.py` | byte-identical duplicate clusters, mapping, review queue and summary |
| 2 | `url_canonical.py` | `build_url_resolution.py` | canonical URL groups and the URL-level duplicate mapping |
| 3 | `near_duplicates.py` | `build_near_duplicates.py` | near-duplicate pairs/clusters, resolutions and review queue |
| 4 | `syndication.py` | `build_syndication.py` | syndicated-copy families and relationships |
| 5 | `versioning.py` | `build_versioning.py` | article-version families, relationships and temporal availability |
| 6 | `cluster_validation.py` | `build_cluster_validation.py` | validated clusters, conflicts and their review queue |
| 7 | `canonical_selection.py` | `build_canonical_selection.py` | one canonical article per cluster, with the selection report |
| 8 | `mapping_layer.py` | `build_mapping_layer.py` | the consolidated, provisionally frozen duplicate mapping (audit + manifest) |

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

## Hand-off and verification

Step 8's frozen mapping and step 7's canonical selection are what the corpus
release consumes: `src/news_collection/canonical_corpus_release(_v2).py`
builds the one-per-news-item article universe from them, and that release is
what the feature tables and the LLM extraction read. The offline test suite
for this package:

```bash
.venv/bin/python -m pytest tests/test_exact_duplicates.py \
    tests/test_url_resolution.py tests/test_near_duplicates.py \
    tests/test_syndication.py tests/test_versioning.py \
    tests/test_cluster_validation.py tests/test_canonical_selection.py \
    tests/test_mapping_layer.py -q
```

## Discipline

A duplicate is never deleted — it is mapped to its canonical copy, so the
grouping is auditable and reversible. Near-duplicate and syndication decisions
are validated (step 6) before the mapping is frozen (step 8). See `REPO_MAP.md`.
