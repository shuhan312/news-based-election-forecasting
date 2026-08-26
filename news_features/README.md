# `news_features/` — feature tables and frozen news evidence

This directory holds two things: the **Layer 4 feature-table outputs** built from
the labelled corpus, and the **Layer 6 frozen evidence** for every news result
the report cites — one register-numbered subdirectory per experiment, each with
its results JSON and a `findings.md`. (In `REPO_MAP.md`, Layer 4 is the code in
`src/news_features/` that produces the tables, and Layer 6 is the frozen
experiment evidence that lives here.) It is the home of the reported news facts.
The code that builds it is in `src/news_features/` and `src/news_modelling/`; the
corpus it reads is in `news_collection/`.

## Start here

| Document | What it gives you |
| --- | --- |
| [`PRODUCTION_NEWS_EVIDENCE_REGISTER.md`](PRODUCTION_NEWS_EVIDENCE_REGISTER.md) | The human-readable results register (evidence cut-off 1 Aug 2026): production evidence, superseded pilots, estimates, and what has not been run, kept separate |
| [`ARTIFACT_LINEAGE.md`](ARTIFACT_LINEAGE.md) | Which article universe and feature table are the **production** release, so two incompatible pipelines are never treated as one analysis |
| [`../REPO_MAP.md`](../REPO_MAP.md) | The report-section → artefact → code trace for every reported number |

## Final-report feature tables

The final report uses two frozen feature releases at **election × party ×
period** grain, each containing six non-overlapping windows and six cumulative
periods:

| Release | Corpus | Final-report role |
| --- | --- | --- |
| `news_feature_table_v1.csv` + metadata | the 1,632-article principal-election corpus | frozen pre-enrichment reference |
| `news_feature_table_v2.csv` + metadata | v1 plus 627 by-election articles | enriched confirmatory release and source of the report's main positive results |

The metadata files record the exact canonical corpus release used to build each
table. `v3exp` and `v3party` are later sensitivity variants (local-news lineage
and party-grain content); they do not replace the v1/v2 confirmatory pair.

The older ward-level pilot tables (`article_level_news_features`,
`context_aggregated_features`, …) and the post-unblinding `v4e5local`
exploratory table were removed from `main`; they remain in the git commit
history. See [`ARTIFACT_LINEAGE.md`](ARTIFACT_LINEAGE.md) for the release
boundaries.

## Frozen experiment evidence

Each subdirectory is one experiment, register-numbered in the evidence register,
holding the frozen results plus a `findings.md`. They include the blinded 2026
predictions (`blinded_2026_predictions_v1/`, `v2/`), the confirmatory unblinding,
the placebo and decomposition checks (`identity_placebos_v1/`,
`exploratory_decompositions_v1/`), the minimal-detectable-effect analysis
(`minimal_detectable_effect_v1/`), and the transfer probes
(`haslemere_probe/`, by-election and Woking South families). See the register
and `REPO_MAP.md` for which report section each backs.

## Discipline and provenance

Predictor and outcome columns are separated and a leakage audit accompanies the
feature tables. Large binaries — the frozen blinded prediction files — are kept
local/OneDrive per the IRP large-file rule, with their sha256 committed in the
register and beside them, so every figure stays verifiable without the bulk
file. A missing result is recorded as missing, never as a negative result.
