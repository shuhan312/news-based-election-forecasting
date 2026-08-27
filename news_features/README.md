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

## Frozen experiment evidence — complete index

Each subdirectory is one experiment, register-numbered in the evidence
register, holding the frozen results plus findings. The producer module lives
in `src/news_modelling/` unless noted.

| Directory | Producer | What it backs |
| --- | --- | --- |
| `blinded_2026_predictions_v1/`, `blinded_2026_predictions_v2/` | `run_blinded_2026_predictions(_v2).py` | the frozen pre-unblinding predictions: protocol + sha256 manifest (csv local; audit check 4 verifies the freeze) |
| `unblinding_2026_v1/` | `unblind_2026.py` | the one-time scoring against reality — §5.1 and the confirmatory tables |
| `production_news_experiment_v1/`, `production_news_lopo_v1/`, `production_estimability_v1/` | `production_news_*.py` | the frozen 2017→2021 design experiment, LOPO (Table 11) and the estimability audit (§4.6 thresholds) |
| `identity_placebos_v1/`, `placebo_specifications_v1/`, `stance_volume_margins_v1/`, `combined_specification_v1/` | matching modules | the §5.3/§6.2 signal-decomposition diagnostics (Table 15) |
| `exploratory_decompositions_v1/`, `reform_decomposition_v1/`, `per_party_bootstrap_v1/` | matching modules | §5.4 and Figure 5: attribution, mechanism and the per-party split with intervals |
| `stage1_party_sensitivity_v1/`, `byelection_enrichment_v1/` | matching modules | §6.2 (0.2404→0.3004/0.0428) and §6.3 (reliability figures) |
| `approach_comparison_v1/` | `compare_news_approaches.py` | residual vs joint, Table 4 |
| `local_v3_rerun_v1/`, `minimal_detectable_effect_v1/` | matching modules | pack tables t19/t23 — committed, not cited in the final report text |
| `haslemere_probe/`, `woking_south_blind_v1/` | probe/blind modules | §5.6 transfer and replication (Table 14); Woking South includes the sealed protocol, blind predictions and unseal record |
| `synthetic_scenarios_v1/` | `synthetic_news_scenarios.py` | the what-if scenarios the app and viva pack read |
| `pipeline_overview_v1/` | `pipeline_overview_figure.py` | the Figure 2 source data |

### Root registers and diagnosis records

| File | What it is |
| --- | --- |
| `PRODUCTION_NEWS_EVIDENCE_REGISTER.md`, `ARTIFACT_LINEAGE.md` | the results register and the release-boundary record (see Start here) |
| [`CHALLENGE_RESPONSE_FINDINGS.md`](CHALLENGE_RESPONSE_FINDINGS.md) | the 5 August supervisor-challenge response: every figure re-derived from a committed artefact, with earlier errors recorded rather than replaced |
| `PARTY_IDENTITY_AND_DESIGN_POWER.md` | the party-identity and design-power analysis behind the §6.2 interpretation |
| `news_layer_capability_findings.md`, `article_area_attribution_summary.json`, `feature_grain_diagnosis.json` | the grain-decision evidence (§6.4's 68-of-1,632 area finding and the training-cell counts) |

## Discipline and provenance

Predictor and outcome columns are separated. Table metadata records the grain,
usable columns and provenance, while the separate cross-layer audit at
`outputs/leakage_provenance_audit_v1.json` checks chronology, duplicates,
outcome isolation and party identity. Large binaries — the frozen blinded prediction files — are kept
local/OneDrive per the IRP large-file rule, with their sha256 committed in the
register and beside them, so every figure stays verifiable without the bulk
file. A missing result is recorded as missing, never as a negative result.
