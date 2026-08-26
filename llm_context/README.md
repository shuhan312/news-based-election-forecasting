# `llm_context/` — LLM extraction outputs and decision records

Pipeline layer 3 products. This directory holds the results of the Claude context
extraction (`src/llm_extraction/`): the prompts, schemas, the human-agreement
validation, the audits, and the frozen label manifest. It is the evidence that
the LLM labels were validated before use, and the record of which frozen outputs
downstream layers read.

## What is committed vs local

The **raw per-article LLM responses reproduce article quotations**, so under the
copyright policy they are kept local/OneDrive (git-ignored): `d4_llm_outputs*.json`,
`corpus_extraction_outputs_*.json` and the per-layer `*_outputs.json`. The
feature builders read the frozen tranche outputs directly; the older
`llm_context_layer_final.json` is an archived eight-layer pilot freeze and is
not part of the v1/v2 production path.
What **is committed** is everything needed to audit and verify them without the
text:

| File(s) | What it is |
|---|---|
| `context_extraction_prompt_v1_final.md`, `*_schema_v1.json` | The frozen prompts and the label schemas |
| `d4_agreement_report.json`, `*_agreement*.json`, the rescue agreement files | Claude-vs-human agreement (the validation gate figures) |
| `*_audit.md`, `*_error_analysis.md` | Per-layer audits and error analysis |
| `corpus_extraction_batch_digests.json`, `d4_llm_output_manifest.json`, `*_batch*.json` | Batch ids, prompt fingerprints and the `sha256` of each raw output — so the local file can be verified as the one described |

## Reproducibility

Extraction calls the Claude API in batches and is a **frozen artefact**, not a
deterministic re-run (repeating it costs API budget and need not reproduce
identical text). The committed digests and manifests pin exactly which frozen
outputs were used, and every agreement figure recomputes from them. See
`src/llm_extraction/` for the code and `REPO_MAP.md` for how the frozen labels
flow into `src/news_features/`.

## Discipline

Labels enter the pipeline only after human-agreement validation; a dropped
extraction layer keeps its batch ids and computed agreement (traceability) even
though its raw outputs feed nothing. Reform UK and UKIP are kept separate
throughout.
