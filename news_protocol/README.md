# `news_protocol/` — the news-pipeline design authority

The rules, methodologies, pre-registrations and feasibility studies that govern
the news side of the project. This directory answers "why is it done this way?"
— it is the design authority the code in `src/` implements, kept separate from
the code and its outputs so a decision can be read without reading the program.

## Protocol and scope

| Document | What it fixes |
| --- | --- |
| `news_research_protocol.md` | The overall news research protocol |
| `news_analysis_scope_decision.md` | Which elections the news layer covers, and why |
| `raw_news_schema.md`, `raw_news_schema.json` | The raw-news record schema |
| `source_adapter_framework.md`, `news_source_registry.csv` | The source-adapter design and the registry of news sources |

## Eligibility and sampling

| Document | What it fixes |
| --- | --- |
| `article_eligibility_rules.md` | What counts as an eligible pre-election article |
| `eligibility_manual_review_codebook.md`, `eligibility_manual_review_methodology.md` | The human-review codebook and method — the basis for the κ agreement checks |
| `division_sample.md`, `division_sample.csv` | The pre-registered division sampling design (why the ward-tier work is restricted to a sample) |
| `historical_coverage_audit.csv` | The audited news-coverage-back-to date per source |

## Feasibility and specification

| Document | What it fixes |
| --- | --- |
| `residual_model_feasibility.md` | Approach A feasibility — the join between Stage 1 and the news corpus |
| `five_specification_pipeline.md` | The five model specifications, and two joins that were wrong |
| `feature_selection_findings.md` | What the feature table can and cannot support |
| `llm_v2_feasibility_plan.md` | The LLM classifier v2 development and supervisor decision plan |
| `retrieval_validation_report.md` | The retrieval-framework validation report |
| `collection_faults_and_corrections.md` | Faults found in collection and what they cost — kept as an honest record |

`evidence/` holds supporting evidence for these decisions. See `REPO_MAP.md` for
how the protocol governs the collection, cleaning, LLM and feature layers.
