# `src/llm_extraction/` — validated LLM context extraction (Layer 3)

This directory turns canonical news articles into structured context labels,
tests those labels against human coding and independent model runs, and admits
only validated fields to the final feature pipeline. Not every file is part of
the production path: the complete file guide below groups every module by
function, and the main line is listed first.

Generated outputs and decision records live in
[`llm_context/`](../../llm_context/README.md). Raw per-article model responses
remain local because they reproduce copyrighted article quotations.

## 1. The main line

The final report uses three validated extraction layers, run by one
authoritative production runner:

| Final layer | Definition | Production model | Final use |
|---|---|---|---|
| Issue classification | `issue_classification.py` | Claude Sonnet 5 | exploratory issue features |
| Revised party stance | `stance_rescue.py` | Claude Haiku 4.5 | party article share and stance balance |
| Revised framing | `frame_rescue.py` | Claude Haiku 4.5 | validated frames used in exploratory analysis |

`run_corpus_extraction.py` submits, collects, validates, retries, and records
prompt fingerprints for these layers in tranche files named
`llm_context/corpus_extraction_outputs_<tranche>.json`.
`health_check_tranche.py` applies the predeclared operational checks before a
tranche is accepted, and `write_batch_manifest_digest.py` reduces local batch
manifests to committed provenance digests.

```bash
python3 -m src.llm_extraction.run_corpus_extraction submit <tranche>
python3 -m src.llm_extraction.run_corpus_extraction collect <tranche>
python3 -m src.llm_extraction.health_check_tranche <tranche>
```

The accepted labels have two frozen downstream releases:

| Release | Builder | Outputs | Role in the final report |
|---|---|---|---|
| v1 | [`src/news_features/build_feature_table.py`](../news_features/build_feature_table.py) | `news_features/news_feature_table_v1.csv`, `news_feature_table_v1_metadata.json` | frozen pre-enrichment reference |
| v2 | [`src/news_features/build_feature_table_v2.py`](../news_features/build_feature_table_v2.py) | `news_features/news_feature_table_v2.csv`, `news_feature_table_v2_metadata.json` | enriched confirmatory release including the by-election corpus |

End-to-end:

```text
run_corpus_extraction.py
    -> llm_context/corpus_extraction_outputs_<tranche>.json
    -> build_feature_table.py / build_feature_table_v2.py
    -> news_features/news_feature_table_v1.csv / news_feature_table_v2.csv
    -> src/news_modelling/run_blinded_2026_predictions.py / _v2.py
    -> news_features/blinded_2026_predictions_v1/ / _v2/
    -> src/news_modelling/unblind_2026.py
    -> news_features/unblinding_2026_v1/
```

## 2. Complete file guide, grouped by function

### 2.1 Production pipeline (the main line)

| File | Role |
|---|---|
| `run_corpus_extraction.py` | the authoritative runner: full-corpus extraction of the three layers that survived the validation gate |
| `issue_classification.py` | issue/topic layer definition: prompt, schema, and per-record validator |
| `stance_rescue.py` | revised three-level party-stance layer definition (replaced the failed original) |
| `frame_rescue.py` | revised framing layer definition (replaced the failed original) |
| `health_check_tranche.py` | operational gate a tranche must pass before its labels are accepted |
| `write_batch_manifest_digest.py` | reduces a tranche's local batch manifest to the committed provenance digest |

### 2.2 Shared helpers imported by the code above

| File | Role |
|---|---|
| `pilot_sample.py` | sampling and prompt-construction functions; also drew the D4 validation sample |
| `run_pilot.py` | article loading and model constants reused by the production runner and every rescue layer |
| `validate_context.py` | schema validation for extracted records |

### 2.3 Validation evidence behind the report's agreement table

These scripts produced the kappa values and pass/fail decisions reported in
the final report (Appendix, LLM extraction validation).

| File | Role |
|---|---|
| `build_d4_sample.py` | draws the deterministic human-validation article sample |
| `run_d4_validation.py` | runs the six compared extraction layers over that sample for both models |
| `compare_d4_agreement.py` | scores model output against human labels; defines the kappa >= 0.60 judge reused by every other scorer |
| `compare_model_to_model.py` | inter-model (Sonnet vs Haiku) reliability on the compared layers |
| `compare_stance_rescue.py` | scores the revised stance layer (inter-model, then human reference) |
| `compare_frame_rescue.py` | scores the revised framing layer (inter-model, then human reference) |
| `test_coarsened_agreement.py` | pre-stated check of whether failing fields pass at coarser label granularity |

### 2.4 Negative-result evidence (excluded layers)

The credit-blame and expected-impact layers failed their gates even after a
redesign. Their code remains because the final report reports those negative
results, which must stay reproducible; they are evidence, not production
layers.

| File | Role |
|---|---|
| `credit_blame.py` | original credit/blame attribution layer definition |
| `attribution_rescue.py` | redesigned credit/blame layer (second attempt) |
| `compare_attribution_rescue.py` | scores the redesign against human gold labels (still below gate; excluded) |
| `electoral_consequence.py` | original expected-electoral-impact layer definition |
| `consequence_rescue.py` | redesigned expected-impact layer (second attempt) |
| `compare_consequence_rescue.py` | scores the redesign against human gold labels (still below gate; excluded) |

### 2.5 Superseded schemes retained as validation inputs

| File | Role |
|---|---|
| `stance_classification.py` | original stance scheme that failed validation; imported by `run_d4_validation.py` as a compared arm |
| `framing_detection.py` | original framing scheme that failed validation; imported by `run_d4_validation.py` as a compared arm |
| `temporal_horizon.py` | LLM temporal-horizon layer that was not adopted; imported by `run_d4_validation.py` as a compared arm |

### 2.6 Final-report extensions

Thin wrappers that reuse the frozen three-layer machinery on additional
final-report samples; they define no new extraction methods.

| File | Role |
|---|---|
| `run_byelection_extraction.py` | extracts the by-election corpus that enters the v2 feature table |
| `run_byelection_issues_resubmit.py` | recovery wrapper: resubmits the by-election issues layer after an API credit outage |
| `run_haslemere_probe_extraction.py` | extraction for the Haslemere replication test |
| `run_woking_south_blind_extraction.py` | extraction for the Woking South blind transfer test |

### 2.7 Reform UK sub-field validation addendum

| File | Role |
|---|---|
| `build_reform_subfield_sample.py` | builds the human-annotation workbook for the reform_uk sub-field block |
| `compare_reform_subfields.py` | scores the sub-field block against those human labels |

This block did not enter the final production extraction; the feature layer
uses a deterministic Reform-mention indicator instead.

### 2.8 Archived validation support and the post-unblinding extension

| File | Role |
|---|---|
| `freeze_layer.py` | pure validation helpers retained because the archived eight-layer freeze report and the viva pack exercise its evidence re-verification; it is not a production runner |
| `run_e5_backlog_v3_extraction.py` | post-unblinding v3exp lineage: not used by the v1/v2 feature tables, but its labels enter the v3exp table that the Woking South blind test's local arm (§5.6) fits on |

Superseded development code beyond this — the original single-layer pilot
runners, the never-validated local/national-relevance and confidence-evidence
layers, the obsolete eight-layer freeze runner, and two one-off provenance
repair tools — has been removed from the final tree. Git history preserves
those scripts. The prompt-backfill finding, including the unrecoverable v1.2
prompt, remains recorded in `llm_context/d4_findings_log.md`.

## 3. Output locations and hand-off

The production code and its outputs deliberately live in different
directories:

| Location | Contents | Version-control status |
|---|---|---|
| `src/llm_extraction/` | extraction, validation and comparison code | committed |
| `llm_context/corpus_extraction_outputs_<tranche>.json` | raw per-article labels and supporting quotations | local/OneDrive; git-ignored because quotations reproduce copyrighted text |
| `llm_context/*agreement*.json` | human-model and model-model validation results | committed |
| `llm_context/corpus_extraction_batch_digests.json` | prompt fingerprints, batch ids and output digests | committed |
| `llm_context/d4_llm_output_manifest.json` | integrity manifest for local validation outputs | committed |
| `news_features/news_feature_table_v1.*` | frozen pre-enrichment feature table and metadata | committed |
| `news_features/news_feature_table_v2.*` | enriched final-report feature table and metadata | committed |

## 4. Verifying this directory without spending API credit

The deterministic logic of this package (prompt construction, record
validators, agreement scoring, gate rules) is covered by unit tests that run
offline in a few seconds:

```bash
python -m pytest tests/test_issue_classification.py \
    tests/test_stance_classification.py tests/test_framing_detection.py \
    tests/test_credit_blame.py tests/test_electoral_consequence.py \
    tests/test_temporal_horizon.py tests/test_freeze_layer.py \
    tests/test_llm_context_schema.py tests/test_pilot_pipeline.py \
    tests/test_party_content_attribution.py
```

The model responses themselves are treated as frozen artefacts rather than
regenerated casually: the Claude Batches API is costly and not bit-for-bit
deterministic. Committed prompt versions, agreement scorecards, batch
digests, prompt fingerprints, and SHA-256 manifests identify the exact local
outputs used by the final feature tables.

The final methodological rule is simple:

1. validate the record structure and evidence;
2. measure reliability on held-out human-labelled articles and independent
   model runs;
3. admit only fields that meet the declared rule;
4. preserve failed fields only when they support a reported negative result;
5. make every accepted tranche traceable to its prompt and batch manifest.

See [`REPO_MAP.md`](../../REPO_MAP.md) for the complete path from canonical
articles through extraction and feature construction to the Stage 2 models.
The Stage 2 runners also load the frozen Stage 1 bundle documented in
[`surrey-election-no-news-baseline/README.md`](../../surrey-election-no-news-baseline/README.md).
