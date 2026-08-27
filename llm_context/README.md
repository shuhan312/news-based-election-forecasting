# `llm_context/` — LLM extraction outputs and decision records

Pipeline layer 3 products. This directory holds the results of the Claude
context extraction (`src/llm_extraction/`): the prompts, schemas, the
human-agreement validation, the audits, and the frozen label manifests. It is
the evidence that the LLM labels were validated before use, and the record of
which frozen outputs downstream layers read. The complete index below groups
every committed file by role; the two final sections are explicitly
historical.

## What is committed vs local

The **raw per-article LLM responses reproduce article quotations**, so under
the copyright policy they are kept local/OneDrive (git-ignored):
`d4_llm_outputs*.json`, `corpus_extraction_outputs_*.json` and the per-layer
`*_outputs.json`. What is committed is everything needed to audit and verify
them without the text: prompts, schemas, agreement scorecards, batch digests
and SHA-256 manifests. Extraction calls the Claude API in batches and is a
**frozen artefact**, not a deterministic re-run; every agreement figure
recomputes from the committed files, and the digests pin exactly which frozen
outputs the feature tables used.

The evidence granularity is one record per extraction layer, per model arm
and per gate (audit, error analysis, schema, batch manifest, agreement
verdict); each validation conclusion in the final report's agreement table
therefore has its own checkable source file.

## 1. Production extraction (the main line)

Written by `src/llm_extraction/run_corpus_extraction.py`,
`health_check_tranche.py` and `write_batch_manifest_digest.py`.

| File | What it is |
|---|---|
| `context_extraction_prompt_v1_final.md` | the frozen production prompt |
| `llm_prompt_version_v1.1.md` | the prompt version record |
| `issue_taxonomy_v1.3.json` | the production issue taxonomy (loaded by `issue_classification.py`) |
| `corpus_extraction_batch_digests.json` | per-tranche batch ids, prompt fingerprints and output digests |
| `tranche_health_check_narrow/far/far2/far3/all.json` | the predeclared operational gate each tranche passed before acceptance |
| `llm_context_version_manifest.json` | the version index for the extraction contract |

## 2. D4 validation — the evidence behind the report's agreement table

Produced by `build_d4_sample.py`, `run_d4_validation.py`,
`compare_d4_agreement.py`, `compare_model_to_model.py` and
`test_coarsened_agreement.py`; these files are the source of every kappa in
the final report's LLM-validation appendix.

| File | What it is |
|---|---|
| `d4_validation_sample_v1.csv`, `d4_validation_sample_audit.json` | the deterministic human-validation sample and its audit |
| `d4_human_labels_v1.csv` | the human annotations |
| `d4_agreement_report.json` / `_haiku.json` | model-vs-human agreement per arm (`{SUFFIX}` filenames are written by the scorer) |
| `d4_inter_model_agreement.json` | Sonnet-vs-Haiku reliability |
| `d4_coarsened_agreement.json` / `_haiku.json` | the pre-stated coarse-granularity check |
| `d4_findings_log.md`, `d4_gate_outcome_and_decisions.md` | the findings log and the recorded gate decisions |
| `d4_llm_output_manifest.json` | SHA-256 manifest of the local validation outputs |

## 3. Adopted redesigns (stance and framing)

The revised three-level stance and revised framing layers that replaced the
failed originals and entered production.

| File | What it is |
|---|---|
| `stance_rescue_batch.json` / `_batch_haiku.json`, `frame_rescue_batch.json` / `_batch_haiku.json` | batch manifests of the redesign runs (written with a per-model suffix) |
| `stance_rescue_outputs.json` / `_haiku.json`, `frame_rescue_outputs.json` / `_haiku.json` | the redesign outputs used for scoring |
| `stance_rescue_agreement.json` + `.md`, `frame_rescue_agreement.json` + `.md` | the agreement verdicts that admitted both layers |

## 4. Negative-result evidence (excluded layers)

The credit-blame and expected-impact layers failed their gates even after a
redesign; the final report cites these negative results, so their evidence
stays reproducible.

| File | What it is |
|---|---|
| `attribution_rescue_batch.json` / `_batch_haiku.json`, `attribution_rescue_agreement.json` | the credit-blame redesign run and its below-gate verdict |
| `consequence_rescue_batch.json` / `_batch_haiku.json`, `consequence_rescue_outputs_haiku.json`, `consequence_rescue_agreement.json` | the expected-impact redesign run and its below-gate verdict |

## 5. Reform UK sub-field validation addendum

| File | What it is |
|---|---|
| `reform_subfield_human_labels_v1.csv` | the human annotations for the sub-field block |
| `reform_subfield_agreement.json` / `_haiku.json` | the scored verdicts (the block did not enter production; the feature layer uses a deterministic Reform indicator) |

## 6. Schema, rules and taxonomy version chain (interpretation keys)

These files interpret version stamps inside the frozen outputs; older
versions are retained because stamped records refer to them.

| File | What it is |
|---|---|
| `llm_context_schema_v1.json` | the enforced record contract, loaded by `validate_context.py` |
| `llm_context_validation_rules_v1.md`, `llm_context_validation_rules_v1.1.md` | the validation rules; v1.1 supersedes v1 for new extractions, while pilot outputs validated under v1 remain as recorded |
| `issue_taxonomy_v1.2.json` | the pre-v1.3 taxonomy — rule S7 forbids national codes under pre-v1.3 stamps, so this file is the key for reading stamped records |
| `llm_context_schema_documentation_v1.md`, `llm_context_schema_revision_notes.md`, `llm_context_schema_v1.1_to_v1.2_changes.md` | the schema documentation and revision history |
| `llm_context_changelog.md` | the layer-by-layer change log |
| `issue_layer_decisions_v1.md`, `phase6_research_decisions_v1.md` | the recorded issue-layer and phase-6 research decisions |

## 7. Pilot-era records (historical — the eight-layer pilot, 26–27 July)

The pilot that tested eight candidate layers before the D4 gate reduced them.
These are frozen decision records: they explain why each layer was kept,
redesigned or dropped. None of them is on the production path.

| File(s) | What it is |
|---|---|
| `llm_context_pilot_audit.md`, `llm_context_pilot_sample_v1.csv` | the 67-article pilot audit and its sample |
| `llm_context_revalidation_report.md`, `llm_context_revalidation_sample_v1.csv` | the pilot revalidation pass |
| `llm_context_error_analysis.md`, `llm_context_example_outputs_v1.json` | the cross-layer error analysis and worked example outputs |
| `issue_classification_audit.md` + `_error_analysis.md` + `_schema_v1.json` | pilot audit of the issue layer (kept for production after D4) |
| `stance_classification_*`, `framing_detection_*` (audit, error analysis, schema) | pilot records of the original stance/framing schemes that failed and were replaced by the rescues |
| `credit_blame_*`, `electoral_consequence_*` (audit, error analysis, schema) | pilot records of the two layers whose failure the report cites |
| `local_national_relevance_*`, `confidence_evidence_*`, `temporal_horizon_*` (audit, error analysis, schema where present) | pilot records of the three candidate layers dropped without redesign |

## 8. Legacy freeze family (historical — pre-tranche eight-layer freeze)

| File | What it is |
|---|---|
| `llm_context_freeze_report.md` | the report of the one legacy eight-layer freeze (its runner is retained in Git history; `freeze_layer.py`'s evidence re-verification is what the viva pack demonstrates) |
| `llm_context_schema_v1_final.json` | the freeze-date schema snapshot that accompanied that freeze; not read by the v1/v2 production path |

## Discipline

Labels enter the pipeline only after human-agreement validation; a dropped
extraction layer keeps its batch ids and computed agreement (traceability)
even though its raw outputs feed nothing. Reform UK and UKIP are kept separate
throughout. See `src/llm_extraction/README.md` for the code-side guide and
`REPO_MAP.md` for how the frozen labels flow into `src/news_features/`.
