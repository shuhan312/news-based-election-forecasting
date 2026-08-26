# `src/news_features/` — the feature-construction code

Pipeline layer 4 (news side): turn the labelled article corpus into the
election–party–window **feature tables** the model joins against, with a leakage
audit. This directory is **code only**. The tables it produces live at the
repository root in [`news_features/`](../../news_features/README.md); the
labelled corpus it reads is in `llm_context/` and `news_collection/`.

## How the files relate (at a glance)

One engine, imported by five thin wrappers; two diagnostics stand to the side.
Nothing here imports anything else in the layer.

```
llm_context/corpus_extraction_outputs_*.json      (frozen LLM labels)
news_collection/canonical_corpus_release_*.json   (frozen corpus)
        │
        ▼
build_feature_table.py  ── the ENGINE ──────────► news_feature_table_v1.csv
   load → freeze → guard → accumulate                (frozen pre-enrichment ref)
        → emit → reporting-gate → write
   imports one helper: actor_party_attribution.py
        │   each wrapper = `import build_feature_table as frozen`,
        │   rebind a few globals, call frozen.main() — the chain never changes
        ├─ build_feature_table_v2.py       ─► v2.csv     ★ main confirmatory results
        ├─ build_feature_table_v3exp.py    ─► v3exp.csv    local sensitivity (App. Table 9) + Woking South
        ├─ build_feature_table_v3party.py  ─► v3party.csv  party-grain → placebo / decomposition / stance
        ├─ build_haslemere_probe_features.py     ─► Haslemere holdout   (report §5.6)
        └─ build_woking_south_blind_features.py  ─► Woking South holdout (report §5.6)

diagnose_article_area_attribution.py ─► 4.2% / 94.2% area finding (justifies the grain, §6.4)
diagnose_feature_grain.py            ─► training-cell counts
   (both read the corpus directly — not part of the build, no output feeds a table)
```

The rest of this README expands each box: the engine, the wrappers, the seven
ordered steps inside `main()`, and why the grain is not ward-level.

## The production feature table is built by one engine

The feature table the Stage 2 model joins is built by a single engine,
**`build_feature_table.py`**. It reads the frozen LLM extraction tranches
(`llm_context/corpus_extraction_outputs_*.json`) and the frozen canonical
corpus release, deduplicates records (newest tranche wins), and aggregates them
**inline** to the `(election, party, window)` grain. Every aggregation rule, the
zero-cell policy, the local/national arm split, and the training-variation
reporting gate live inside `build_feature_table.py` itself — it does **not**
orchestrate a chain of importable stage modules.

Running `build_feature_table.py` **is** the v1 build. Every other production
table is a thin wrapper that imports the engine (`import build_feature_table as
frozen`), rebinds a few module globals (corpus source, output paths, split
roles, the election grid) and calls `frozen.main()`:

| File | Output table | Role in the final report |
| --- | --- | --- |
| `build_feature_table.py` | `news_feature_table_v1.csv` | the **engine**; frozen pre-enrichment reference |
| `build_feature_table_v2.py` | `news_feature_table_v2.csv` | enriched confirmatory release (+8 by-elections) — **the main results** |
| `build_feature_table_v3exp.py` | `news_feature_table_v3exp.csv` | local-news lineage (+29 reviewer-admitted local articles); the **reported local sensitivity** (`local_v3_rerun.py`, Appendix Table 9) and the Woking South case study read it |
| `build_feature_table_v3party.py` | `news_feature_table_v3party.csv` | party-grain content table (turns on `PARTY_CONTENT_ATTRIBUTION`); **every party-level exploratory / placebo / decomposition analysis reads it** (`identity_placebos`, `reform_decomposition`, `stance_volume_*`, `stage1_party_sensitivity`, `placebo_specifications`, …) |
| `build_haslemere_probe_features.py` | Haslemere probe features | case-study holdout features, reusing the engine (kept separate for blindness) |
| `build_woking_south_blind_features.py` | Woking South features | case-study holdout features, reusing the engine (kept separate for blindness) |

`actor_party_attribution.py` is the only helper the engine imports. It is active
**only** when `PARTY_CONTENT_ATTRIBUTION` is on (the `v3party` wrapper); in the
v1/v2 confirmatory builds it is imported but dormant.

The production tables are named and reconciled in
[`news_features/ARTIFACT_LINEAGE.md`](../../news_features/ARTIFACT_LINEAGE.md).
The report evaluates **v1 and v2 side by side; v2 supplies the main positive
confirmatory results.**

## The logic chain, in order

Layer 4 is one deterministic pass inside `build_feature_table.py` (`main()`): it
reads frozen upstream files and writes one feature table. There is no chain of
stage scripts to run — the steps below are the ordered operations *inside* that
one file.

1. **Load labels** — `load_records()` reads every
   `llm_context/corpus_extraction_outputs_*.json`, keeps only the live
   (non-excluded) extraction layers, deduplicates on `article_id` with the
   **newest tranche winning**, and honours any `superseded_layers`.
   → accepted records per layer, plus provenance (which tranche and prompt each
   came from).
2. **Freeze the corpus** — `build_release()` unions the main, pilot and
   validation eligibility streams and applies dates, principal-election scope,
   the six windows and text availability.
   → the canonical article universe and `corpus_size`.
3. **Two guards** — every extraction article must lie inside the release
   (`unexpected_ids` stops the build), and the deduplicated article count must
   not exceed `corpus_size` (a silent double-count would inflate every volume
   feature).
4. **Accumulate** — one pass over the articles fills three counters:
   `election_cells` (article, issue and framing counts, per election × window),
   `party_cells` (party article count and portrayal, taken from the **stance
   layer's own per-party judgements**), and `party_arm_cells` (the same, split
   by local / national collection arm).
5. **Emit rows** — one row per `(election, party, period)` across the six
   windows and six cumulative snapshots: it computes `party_article_share`,
   `net_portrayal` and `net_portrayal_share`, **retains zero-article cells**
   (count `0`, blank share), emits the local/national columns, and asserts
   `local + national == combined` on every row.
6. **Reporting gate** — `training_variation` counts distinct training values per
   column *within a period*: `< 3` insufficient, `< 10` fittable-not-reportable,
   `>= 10` usable. In v1/v2 exactly the **12 party-level columns** pass.
7. **Write** — the `news_feature_table_*.csv` (LF-pinned, byte-stable) and its
   `*_metadata.json`.

The `__main__` block sets `EXCLUDED_TRANCHES = V1_EXCLUDED_TRANCHES` and calls
`main()` — that is the v1 build. Each wrapper repeats this **exact** chain
against a different corpus or holdout; nothing in the chain changes.

### What the other files do

- **Wrappers** (`_v2`, `_v3exp`, `_v3party`, `build_haslemere_probe_features`,
  `build_woking_south_blind_features`) — import the engine, rebind a few globals,
  re-run steps 1–7. See the table above for which report result each feeds.
- **`actor_party_attribution.py`** — helper the engine imports; active only in
  the `v3party` wrapper (`PARTY_CONTENT_ATTRIBUTION` on), dormant in v1/v2.
- **Diagnostics** — `diagnose_feature_grain.py` and
  `diagnose_article_area_attribution.py` (the grain-decision evidence the report
  cites; both read the corpus directly, independent of the build).

## The grain, and why it is not ward-level

The brief asks for features per ward. The corpus cannot deliver that: only about
**4.2%** of canonical articles carry an unambiguous Surrey area, and **94.2%**
name no unambiguous area at all. The table is therefore keyed on
`(election, party, window)`; joining it to the baseline's `(election, area,
party)` rows broadcasts each value across the areas of its election. A news
feature here can explain differences **between elections and between parties,
never between areas within an election** — a limitation stated in the builder's
docstring rather than hidden behind a feature name.

Two consequences follow, both handled inside the engine:

- **Counts and shares, both.** A count is contaminated by how deeply a contest
  was searched; a share is not. Every count column ships with a companion share.
- **Zero-article cells are retained explicitly.** A completed search that found
  no eligible article is kept as a row with count `0` and a **blank** share
  (a zero denominator is undefined, not a share of zero) — missing coverage is
  represented, never silently filled or dropped.

Each feature also carries a `training_variation` verdict computed from the table
itself (`insufficient` / `fittable_not_reportable` / `usable`), so only columns
that actually vary across training rows are offered to a model. In v1/v2 this
leaves the **12 party-level share / net-portrayal columns** as `usable`; the
election-level issue and framing columns are `insufficient`/`fittable` and are
excluded from the reported models.

## Removed from main: the ward-level pilot and post-unblinding probes

An earlier **67-article, ward-level pilot** (`alignment` / `time_windows` /
`scope_classification` / `article_features` / `context_aggregation` /
`recency_weighting` / `missing_news` and their `run_*` runners), its downstream
(`feature_selection_v1`, `ward_party_election_features_v1`,
`specification_coverage`, `residual_feasibility`, `ward_resolution_v1`), and the
post-unblinding `build_feature_table_v4e5local` / `e5_local_triage` exploratory
builds were **removed from the final `main`**. `build_feature_table.py` imported
none of them and no reported result cited their output. They remain in the git
commit history for audit; nothing on the reproduction path above depends on them.

## Diagnostics

- `diagnose_feature_grain.py` — the training cell counts cited by the builder.
- `diagnose_article_area_attribution.py` — the 4.2% / 94.2% area-attribution
  finding that justifies the election–party–window grain (reads the corpus
  directly, independent of the build).

## Running and outputs

The build is **deterministic**: it reads frozen files, so re-running reproduces
the same tables bit-for-bit (a rebuild test pins v1 and v2). From the repository
root:

```bash
python3 -m src.news_features.build_feature_table       # news_feature_table_v1.csv
python3 -m src.news_features.build_feature_table_v2     # news_feature_table_v2.csv (main)
python3 -m src.news_features.build_feature_table_v3exp  # local-news lineage
python3 -m src.news_features.build_feature_table_v3party # party-grain content table
```

Each writes its `news_feature_table_*.csv` and `*_metadata.json` (rows, corpus
fingerprint, grain, `empty_cell_policy`, `zero_article_cells`,
`training_variation`, `usable_columns`, provenance) into the repository-root
`news_features/` directory.

## Discipline

Predictor and outcome columns are kept separate; missing news is represented
explicitly rather than filled; every feature table ships with a leakage audit
and a data dictionary in `news_features/`. See `REPO_MAP.md` for how the tables
feed Stage 2 modelling.
