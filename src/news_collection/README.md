# `src/news_collection/` — the news collection code

Pipeline layer 1 (news side): retrieve the pre-election news corpus, screen it
for eligibility, and record every keep/drop decision. This directory is **code
only**. The artefacts it produces — the query inventory, the append-only search
log, the eligibility decisions and the corpus statistics — live at the
repository root in [`news_collection/`](../../news_collection/README.md); the raw
corpus itself is in `data/raw/news/` and is not committed. The design authority
for the stages and rules is `news_protocol/`.

## What it does

```text
build_query_inventory      →  deterministic query inventory (775 queries, stages A–M)
run_collection / runner    →  execute queries via adapters (SerpAPI, publisher search, web archives),
                              appending one row per search to search_log.csv (resumable)
assess_eligibility + LLM   →  screen articles to the pre-election window and relevance;
                              the LLM classifier is validated to κ ≥ 0.60 and frozen before corpus use
make_collection_report     →  corpus statistics, schema re-validation, the stage report
```

## Two separate stage systems

Do not confuse them:

- **Collection stages A–M** — groups of the query inventory, run with
  `python3 -m src.news_collection.run_collection --stage A|B|C|D|M`.
- **Eligibility pipeline stages 1–5** — dates → eligibility → review sheet →
  frozen LLM batch → assembly. The principal corpus runs this once; each
  case-study holdout replicates it with the same frozen rules on new paths.

## Key modules

| Module | Role |
| --- | --- |
| `build_query_inventory.py` | Builds the deterministic query inventory from the division sample and results |
| `run_collection.py`, `runner.py`, `adapters.py`, `schema.py` | The staged collection engine and its source adapters and corpus schema |
| `assess_eligibility.py`, `llm_classifier.py` | Pre-election-window and relevance screening; v1 supports the recorded pilot and disagreement evidence |
| `llm_classifier_v2.py`, `llm_v2_io.py` | Frozen eligibility classifier and shared deterministic I/O used by blind validation and production batches |
| `run_llm_classification_pilot.py`, `run_llm_validation_v2.py`, `run_llm_corpus_batch_v2.py` | The recorded pilot, blind validation and frozen full-corpus classification runs |
| `make_collection_report.py` | Diagnostics and the stage report |
| `audit_guardian_geographic_relevance.py`, `audit_serpapi_domain_relevance.py`, `audit_llm_pilot_disagreements.py` | Relevance and disagreement audits |

### Other modules

The remaining scripts are secondary helpers of the same pipeline, grouped by role:

- **Article date resolution** (fixes the pre-election window per article) — `build_effective_dates.py`, `resolve_publication_dates.py`, `recover_pdf_dates.py`
- **Review queues and samples** (the human-review and validation sheets) — `build_full_corpus_review_sheet.py`, `build_manual_review_sample.py`, `finalize_manual_review.py`, `manual_review_schema.py`, `build_llm_validation_sample.py`, `build_e5_local_queue.py`, `build_e5_risk_review_plan.py`, `build_e5_disagreement_review_data.py`, `build_byelection_second_review_queue.py`
- **Agreement measurement** (the LLM-vs-human κ figures) — `compare_llm_to_human_agreement.py`, `compare_llm_validation_agreement.py`, `compute_review_agreement.py`
- **Corpus assembly and release** — `assemble_corpus_decisions.py`, `canonical_corpus_release.py`, `canonical_corpus_release_v2.py`
- **Diagnostics and reporting** — `check_completeness.py`, `measure_window_reach.py`, `catalogue_haslemere_nonnews_trail.py`
- **Case-study helpers** — `run_e5_backlog_v3_assembly.py`, `run_llm_local_extension_v2.py`, `walk_byelection_pipeline.py`

## Case-study probes (frozen rules, new paths)

Each temporal holdout is collected and screened by the same staged pipeline,
kept separate so its blindness is preserved:

- `run_byelection_stages.py` / `run_byelection_llm_batch.py` / `run_byelection_assembly.py`
- `run_haslemere_probe_stages.py` / `run_haslemere_probe_llm_batch.py` / `run_haslemere_probe_assembly.py`
- `run_woking_south_blind_stages.py` / `run_woking_south_blind_llm_batch.py` / `run_woking_south_blind_assembly.py`

## Running and reproducibility

Collection is run per stage:

```bash
python3 -m src.news_collection.run_collection --stage A|B|C|D|M
```

Collection queries **live news APIs and archives**, so it is not
bit-for-bit re-runnable — later runs see a changed news web. The corpus is
therefore a **frozen snapshot**: what is committed is the deterministic query
inventory, the append-only `search_log.csv`, the eligibility decisions and a
`sha256` manifest, not the raw articles. "Reproducible" here means the query
inventory and every keep/drop decision can be regenerated and audited from
committed files — not that the raw corpus can be re-collected identically. The
query inventory rebuilds with
`python3 -m src.news_collection.build_query_inventory` and the diagnostics with
`python3 -m src.news_collection.make_collection_report`.

## Discipline

Every executed search is logged, including zero-result and failed searches;
eligibility is decided by frozen rules and a validated classifier, never
ad hoc; and no article text is committed. See `REPO_MAP.md` for how the corpus
feeds the rest of the pipeline.
