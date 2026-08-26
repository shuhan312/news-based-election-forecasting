# `src/news_collection/` — news collection and eligibility (Layer 1)

Pipeline layer 1 (news side): retrieve the pre-election news corpus, screen it
for eligibility, and record every keep/drop decision. This directory is **code
only**. The artefacts it produces — the query inventory, the append-only search
log, the eligibility decisions and the corpus statistics — live at the
repository root in [`news_collection/`](../../news_collection/README.md); the raw
corpus itself is in `data/raw/news/` and is not committed. The design authority
for the stages and rules is `news_protocol/`. Not every file is part of the
production path: the complete file guide below groups every module by function,
and the main line is listed first.

## 1. The main line

```text
build_query_inventory      →  frozen deterministic query inventory (2,470 queries; A–H, M, M2)
run_collection / runner    →  execute queries via adapters (SerpAPI, publisher search, web archives),
                              appending one row per search to search_log.csv (resumable)
resolve_publication_dates  →  stage 1: fix each article's publication date and confidence
assess_eligibility         →  stage 2: apply the pre-registered I/E rules by script
build_manual_review_sample →  stage 3: the human review sheets for the rules scripts cannot decide
run_llm_corpus_batch_v2    →  stage 4: the frozen κ-validated LLM classifier over the remaining corpus
assemble_corpus_decisions  →  stage 5: merge script, human and LLM decisions into the final record
canonical_corpus_release   →  cut the auditable corpus release the feature layer reads (v2 adds by-elections)
```

```bash
python3 -m src.news_collection.run_collection --stage A|B|C|D|E|F|G|H|M|M2
python3 -m src.news_collection.build_query_inventory
python3 -m src.news_collection.make_collection_report
```

Two separate stage systems — do not confuse them:

- **Collection stages A–H, M and M2** — groups of the query inventory, run with
  `run_collection --stage`.
- **Eligibility pipeline stages 1–5** — dates → eligibility → review sheet →
  frozen LLM batch → assembly. The principal corpus runs this once; each
  case-study holdout replicates it with the same frozen rules on new paths.

## 2. Complete file guide, grouped by function

### 2.1 Collection engine (the main line)

| File | Role |
|---|---|
| `build_query_inventory.py` | builds the deterministic query inventory from the division sample and results |
| `run_collection.py` | CLI entry point for staged collection |
| `runner.py` | executes the query inventory against the adapters, logging every search |
| `adapters.py` | production source adapters (SerpAPI, publisher search, web archives) |
| `schema.py` | record construction and validation for collected articles |

### 2.2 Date resolution

| File | Role |
|---|---|
| `resolve_publication_dates.py` | publication-date resolution stage (date, source, confidence per article) |
| `build_effective_dates.py` | merges every stage of date resolution into one lookup table |
| `recover_pdf_dates.py` | recovers date evidence for the three records whose stored pages lacked it |

### 2.3 Eligibility rules and human review

| File | Role |
|---|---|
| `assess_eligibility.py` | applies the pre-registered inclusion/exclusion rules by script |
| `manual_review_schema.py` | schema, reason-code taxonomy and validation rules for all review sheets |
| `build_manual_review_sample.py` | draws the reproducible stratified review sample (the 168-article pilot) |
| `finalize_manual_review.py` | turns the hand-filled review sheet into committed decisions |
| `compute_review_agreement.py` | percent agreement and Cohen's kappa between independent reviews (shared with `llm_extraction`) |

### 2.4 LLM eligibility classifier — v1 pilot (validation history)

The recorded pilot that justified using an LLM for the E4/E5/E6/E8 rules:
its agreement against the 168 human decisions is the evidence behind the
frozen v2 classifier.

| File | Role |
|---|---|
| `llm_classifier.py` | v1 classifier for the manual-review rules |
| `run_llm_classification_pilot.py` | runs v1 against the same 168 articles the humans coded |
| `compare_llm_to_human_agreement.py` | scores the pilot against the human decisions |
| `audit_llm_pilot_disagreements.py` | row-level audit of every pilot disagreement |

### 2.5 LLM eligibility classifier — frozen v2 (production)

| File | Role |
|---|---|
| `llm_classifier_v2.py` | the frozen v2 classifier definition |
| `llm_v2_io.py` | shared deterministic I/O for every frozen v2 run |
| `build_llm_validation_sample.py` | draws the fresh 128-article blind validation sample |
| `run_llm_validation_v2.py` | runs the frozen v2 once on that blind sample |
| `compare_llm_validation_agreement.py` | scores frozen v2 against the 128 human-coded articles |
| `run_llm_corpus_batch_v2.py` | the frozen v2 batch over the remaining corpus |
| `build_full_corpus_review_sheet.py` | review sheet for the remaining corpus after the batch |

### 2.6 E5 (relevance) exclusion-rule audit

Evidence that the highest-volume exclusion rule was applied correctly.

| File | Role |
|---|---|
| `build_e5_local_queue.py` | the 1,060 local articles that cleared every mechanical rule |
| `build_e5_risk_review_plan.py` | blind, risk-based human-review plan for local E5 |
| `build_e5_disagreement_review_data.py` | assembles the 48 hard E5 disagreements for transparent review |
| `run_llm_local_extension_v2.py` | frozen v2 classifier over the new local backlog |

### 2.7 Corpus assembly and release

| File | Role |
|---|---|
| `assemble_corpus_decisions.py` | merges script, human and LLM decisions into the final eligibility record |
| `canonical_corpus_release.py` | cuts the auditable v1 corpus release the feature layer reads |
| `canonical_corpus_release_v2.py` | v2 release: principal corpus plus the by-elections |

### 2.8 Collection diagnostics and QA audits

| File | Role |
|---|---|
| `make_collection_report.py` | regenerates local corpus diagnostics and re-validates the stored-record schema |
| `audit_guardian_geographic_relevance.py` | flags Guardian records collected before the production-office fix (committed flags CSV) |
| `audit_serpapi_domain_relevance.py` | flags SerpAPI records whose domain cannot be UK-relevant (committed flags CSV) |
| [`audit_leakage_provenance.py`](../../audit_leakage_provenance.py) (repository root) | cross-layer assertions for query lineage, chronology, duplicates, outcome isolation, party identity and the blinded-prediction freeze |

### 2.9 Case-study replications (frozen rules, new paths)

Each temporal holdout replays eligibility stages 1–5 unchanged, kept separate
so its blindness is preserved.

| Chain | Files |
|---|---|
| By-elections (v2 corpus) | `run_byelection_stages.py`, `run_byelection_llm_batch.py`, `run_byelection_assembly.py`, `build_byelection_second_review_queue.py`, `walk_byelection_pipeline.py` (paper walkthrough with committed findings) |
| Haslemere replication (§5.6) | `run_haslemere_probe_stages.py`, `run_haslemere_probe_llm_batch.py`, `run_haslemere_probe_assembly.py`, `catalogue_haslemere_nonnews_trail.py` (descriptive non-news trail) |
| Woking South blind test (§5.6) | `run_woking_south_blind_stages.py`, `run_woking_south_blind_llm_batch.py`, `run_woking_south_blind_assembly.py` |
| Post-unblinding v3exp lineage | `run_e5_backlog_v3_assembly.py` — parallel v3 decisions; not used by the v1/v2 tables, but the v3exp feature table built on them serves the Woking South blind test's local arm (§5.6) |

## 3. Running and reproducibility

Collection queries **live news APIs and archives**, so it is not bit-for-bit
re-runnable — later runs see a changed news web. The corpus is therefore a
**frozen snapshot**: what is committed is the deterministic query inventory,
the append-only `search_log.csv`, the eligibility decisions and a `sha256`
manifest, not the raw articles. "Reproducible" here means the query inventory
and every keep/drop decision can be regenerated and audited from committed
files — not that the raw corpus can be re-collected identically. The inventory
depends on the committed final geographic crosswalk and fails loudly if that
input is absent. `query_lineage_v1.csv` accounts for four logged queries whose
old `-ward` URL slugs were superseded. The 704 unexecuted E/G/H queries remain
explicit planned coverage; they are never treated as zero-result searches.

The machine-readable audit is rebuilt with:

```bash
python3 -m audit_leakage_provenance
```

## 4. Verifying this directory without API credit

The deterministic logic (schemas, review rules, agreement scoring, queue
construction, the frozen classifier's I/O) is covered by offline unit tests:

```bash
python -m pytest tests/test_manual_review.py tests/test_llm_classifier.py \
    tests/test_llm_classifier_v2.py tests/test_llm_local_extension.py \
    tests/test_e5_disagreement_review_data.py tests/test_e5_risk_review_plan.py \
    tests/test_canonical_news_corpus.py tests/test_walk_byelection_pipeline.py
```

A few tests skip themselves on a fresh clone when they need regenerable local
collection state (the skip reasons name the builder that recreates it).

## 5. Discipline

Every executed search is logged, including zero-result and failed searches;
eligibility is decided by frozen rules and a validated classifier, never
ad hoc; and no article text is committed. See `REPO_MAP.md` for how the corpus
feeds the rest of the pipeline.
