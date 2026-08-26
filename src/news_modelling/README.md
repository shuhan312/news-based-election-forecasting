# `src/news_modelling/` — Stage 2 news modelling (Layer 5)

The central test of the IRP: does pre-election news improve prediction beyond the
history-only Stage 1 baseline? This directory fits the news-layer estimator,
freezes its **blinded** 2026 predictions, runs the **one-time unblinding** against
the real results, and carries every post-unblinding diagnostic. It reads the
frozen Stage 1 bundle (`surrey-election-no-news-baseline/outputs/model_bundle_v1/`)
and the v1/v2 feature tables in `news_features/`. Not every file is part of the
prediction path: the complete file guide below groups every module by function,
and the main line is listed first.

## 1. The main line

```text
surrey-election-no-news-baseline/outputs/model_bundle_v1/
    |- out_of_fold_predictions.csv  -> Stage 2 residual training targets
    `- holdout_predictions.csv      -> frozen 2026 Stage 1 baseline

news_features/news_feature_table_v1.csv / news_feature_table_v2.csv
    + Stage 1 bundle
    -> stage1_bundle.py (validation and loading)
    -> news_estimator.py (per-window residual Ridge)
    -> run_blinded_2026_predictions.py / _v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
    -> unblind_2026.py
    -> news_features/unblinding_2026_v1/
```

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions      # freeze v1 predictions
PYTHONPATH=src .venv/bin/python -m news_modelling.run_blinded_2026_predictions_v2   # freeze v2 (enriched) predictions
PYTHONPATH=src .venv/bin/python -m news_modelling.unblind_2026                      # one-time scoring vs reality
```

v1 is the frozen pre-enrichment reference. v2 preserves the same feature and
model specification while adding the by-election corpus and training cells; it
is the enriched confirmatory release behind the final report's main positive
results. `news_estimator.py` implements both declared approaches — **A
(residual)**, which models the residual error of the frozen Stage 1 baseline
and is what v1/v2 froze, and **B (joint)**, compared post-unblinding in
`compare_news_approaches.py` (Appendix Table 4).

## 2. Complete file guide, grouped by function

### 2.1 Core estimation and the blind freeze (the main line)

| File | Role |
|---|---|
| `stage1_bundle.py` | loads and validates the frozen Stage 1 model bundle |
| `news_estimator.py` | the news-layer estimator: Approach A (residual) and Approach B (joint) |
| `window_schemes.py` | the declared news-window schemes, shared across collection, extraction and features |
| `blinded_2026_predictions.py` / `blinded_2026_predictions_v2.py` | construct the blinded prediction records (v1 / v2) |
| `run_blinded_2026_predictions.py` / `run_blinded_2026_predictions_v2.py` | executable freeze entry points; bind input hashes and write the frozen artefacts **before any 2026 outcome is read** |
| `unblind_2026.py` | the authoritative **one-time** unblinding in the main 2026 confirmatory workflow; scores the frozen predictions against reality before the post-unblinding diagnostics run |

### 2.2 Pre-2026 production experiment (design validation)

The frozen 2017→2021 experiment that fixed the Stage 2 design before the 2026
freeze, with its estimability audit and robustness check.

| File | Role |
|---|---|
| `production_estimability.py` + `run_production_estimability.py` | audits whether the production news table can support the planned models (the variation thresholds in §4.6) |
| `production_news_experiment.py` + `run_production_news_experiment.py` | the frozen pre-2026 news comparison |
| `production_news_lopo.py` + `run_production_news_lopo.py` | leave-one-party-out robustness (§5.2, Appendix Table 11) |

### 2.3 Post-unblinding diagnostics (each backs a named report section)

All read frozen inputs; none is imported by the prediction path.

| Module | Question it answers | Report use |
|---|---|---|
| `identity_placebos.py` | is the news layer anything more than the party's name? | §5.3/§6.2 |
| `stage1_party_sensitivity.py` | does the improvement survive removing per-party mean residuals? (0.2404 → 0.3004 / 0.0428) | §6.2 (sole source) |
| `stance_volume_margins.py` | stance vs volume, by margins rather than sign counts | §5.3 |
| `placebo_specifications.py` | does the LLM layer beat counting articles? | §5.3, Appendix Table 15 |
| `combined_specification.py` | does within-party tone survive party identity and volume in one fit? | §6.2 |
| `exploratory_decompositions.py` | attribution and mechanism decompositions | §5.4 |
| `reform_decomposition.py` | per-party ΔMAE decomposition; its JSON drives the split figure | §5.4, Figure 5 (sole source) |
| `per_party_bootstrap.py` | contest-bootstrap uncertainty for the per-party split | §5.4 (pack table t22) |
| `byelection_enrichment.py` | the quantity–quality trade-off of the added by-election cells | §6.3 (reliability figures) |
| `minimal_detectable_effect.py` | what effect size the archived design could detect | design-resolution record (pack table t23); not cited in the final report text |
| `compare_news_approaches.py` | residual (A) vs joint (B), post-unblinding | Appendix Table 4 |
| `local_v3_rerun.py` | the exploratory local-vs-national re-run (v3exp lineage) | pack table t19; not cited in the final report text |
| `haslemere_probe_prediction.py` | the 7 July 2026 transfer probe with frozen v2 specifications | §5.6 |
| `descriptive_2026_targets.py` | recomputes the descriptive targets read by the report table pack | table pack input |

### 2.4 Woking South blind protocol

| File | Role |
|---|---|
| `woking_south_blind_protocol.py` | freezes the protocol before any contact with the outcome |
| `woking_south_blind_predict.py` | produces the blind predictions (no outcome is read); fits the local arm on the hash-pinned v3exp table |
| `woking_south_unseal.py` | the protocol's **only** authorised reader of the outcome |

### 2.5 Report pack and figures

The written report reads only the committed `outputs/report_tables_v1/` and
`outputs/report_figures_v1/`; these modules build them, with build-time
assertions that fail if a number drifts from its frozen source.

| File | Role |
|---|---|
| `build_report_tables.py` | builds the report table pack from committed result artefacts (sha256-pinned manifest) |
| `report_appendix_tables.py` | emits the appendix tables as LaTeX from the table pack |
| `make_report_figures.py` | generates the core report figures from archived results |
| `study_design_figure.py` | Figure 1: how the 24 election events are used |
| `pipeline_overview_figure.py` | Figure 2: the news pipeline end to end |
| `framework_figure.py` | Figure 3: the two-stage framework and freeze line |
| `reform_party_split_figure.py` | Figure 5: Reform vs non-Reform ΔMAE by window |
| `corpus_funnel_figure.py` | proportional-funnel variant of the corpus figure (in the committed figure pack; not included in the final report text) |

### 2.6 Demonstration

| File | Role |
|---|---|
| `synthetic_news_scenarios.py` | what-if news scenarios against the frozen v2 model; read by the Streamlit app and the viva pack |

## 3. Verifying this directory without API credit

Scoring is deterministic: modelling reads frozen inputs (the Stage 1 bundle
and the feature tables), so re-runs reproduce the same numbers, and the
blinded predictions are frozen artefacts with their sha256 committed beside
them. The offline test suite covers the estimator, the freeze/unblind path
and every diagnostic:

```bash
python -m pytest tests/test_news_stage1_bundle.py tests/test_news_window_schemes.py \
    tests/test_blinded_2026_predictions.py tests/test_blinded_2026_predictions_v2.py \
    tests/test_unblind_2026.py tests/test_identity_placebos.py \
    tests/test_combined_specification.py tests/test_placebo_specifications.py \
    tests/test_production_estimability.py tests/test_production_news_experiment.py \
    tests/test_production_news_lopo.py tests/test_per_party_bootstrap.py \
    tests/test_minimal_detectable_effect.py tests/test_artefact_citations.py
```

## 4. Discipline

Predictions are frozen before outcomes are seen; unblinding happens once and is
recorded; the design's minimal detectable effect is archived (pack table t23)
so a null window is never read as proof of no effect; Reform UK is reported
separately and never merged
with UKIP. See `REPO_MAP.md` and `news_features/PRODUCTION_NEWS_EVIDENCE_REGISTER.md`
for which report section each artefact backs.
