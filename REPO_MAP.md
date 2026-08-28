# Repository map

Orientation for readers (examiner, supervisor, future self): what every
directory is for, which report content it backs, and how to trace any
reported number to the code that produced it. The repository is a
staged pipeline, but validation, audit and presentation code may read explicitly
declared upstream artefacts. `tests/test_artefact_citations.py` guards the
machine-readable citation surfaces used by the report table pack and app; it
does not claim to parse every prose citation in the repository.

## The pipeline, layer by layer

| layer | where | what it does |
| --- | --- | --- |
| 1 Collection | `src/` collection entry points, `src/news_collection/`, `news_collection/`, `surrey-election-extractor/` | Builds validated election releases and the news corpus from declared external/raw boundaries; records search, eligibility and leakage decisions |
| 2 Normalisation and deduplication | `src/normalisation/` (Phase 4), then `src/dedup/` (Phase 5) | Standardises names, characters and fields before exact/near-duplicate and version-family handling |
| 3 LLM extraction | `src/llm_extraction/`, `llm_context/` | Runs and validates the issue, stance and framing layers; committed scorecards, digests and manifests preserve the accepted and negative-result evidence, while raw corpus responses remain local |
| 4 Features | `src/news_features/`, top-level `news_features/` | Converts article labels into election-party-window tables. The authoritative release roles are v1, v2, v3exp, v3party, Haslemere and Woking South, as defined in `news_features/ARTIFACT_LINEAGE.md`; also carries feature-level diagnostics and audits |
| 5 Modelling | `src/news_modelling/`, `surrey-election-no-news-baseline/` | Stage 1 history-only candidate modelling; Stage 2 residual modelling; frozen blinded predictions, unblinding, sensitivity analyses and explicitly labelled post-unblinding diagnostics |
| 6 Frozen evidence and protocols | experiment directories under `news_features/`, plus `news_protocol/` | Stores machine-readable results, findings, frozen protocols and pre-registration/deviation evidence used by the final report or its reported negative and sensitivity results |
| 7 Report pack | `outputs/report_tables_v1/`, `outputs/report_figures_v1/`, `news_features/pipeline_overview_v1/` | `build_report_tables.py` writes t01–t23 and a hash manifest; appendix and figure modules produce the report-facing LaTeX and image artefacts from named frozen inputs |
| 8 Consumers | `report/`, `app/`, `demo/` | The report reads the single Layer 7 LaTeX table set directly (no duplicate `report/a*.tex` copies) plus report-facing image copies. The app and viva material may also read explicitly named, citation-guarded upstream artefacts |

Supporting directories include `tests/`, `logbook/`, `deliverables/`,
`scripts/`, `title/` and `data/`. File counts are deliberately omitted because
they change during repository maintenance and are not part of the reproducible
contract. The large number of retained non-code files chiefly reflects frozen
evidence, decision records and the two self-contained election subprojects.

## Report section → artefact → code

| report | frozen artefact (layer 6) | computed by (layer 5) | tables/figures |
| --- | --- | --- | --- |
| §3 data and features | canonical corpus v1/v2, feature-table metadata, division sample | collection and feature pipelines | t17; Appendix a11; `fig0_study_design.png`; `pipeline_overview.png` (`fig0b_corpus_funnel.png` is pack-only) |
| §4 Stage 1 | `surrey-election-no-news-baseline/outputs/model_bundle_v1/` (local) | Stage 1 subproject | t01–t03; Appendix a1 |
| §4 Stage 2 + freeze | `news_features/blinded_2026_predictions_v1/` and `blinded_2026_predictions_v2/` | `run_blinded_2026_predictions.py`, `run_blinded_2026_predictions_v2.py`, `news_estimator.py` | `fig0c_framework.png` |
| §3.2 / Appendix LLM validation | evidence register + `llm_context/` | `src/llm_extraction/` validation runners | Appendix a5 |
| §5.1 confirmatory | `news_features/unblinding_2026_v1/` | `unblind_2026.py` | t04/t05; Appendix a2a/a2b; `fig1_confirmatory_deltas.png` |
| §5.2 sensitivity | unblinding record and `production_news_lopo_v1/` | `unblind_2026.py`, `run_production_news_lopo.py` | t06; Appendix a3/a12/a15/a17 |
| pack-only: local v3 re-run | `local_v3_rerun_v1/` | `local_v3_rerun.py` | t19 (not cited in the final report text) |
| §5.3 diagnostics | `placebo_specifications_v1/`, `identity_placebos_v1/`, `stance_volume_margins_v1/` and party-content results | matching diagnostic modules | Appendix a13; pack-only diagnostic tables/figures remain labelled exploratory |
| §5.4 Reform | `exploratory_decompositions_v1/`, `reform_decomposition_v1/`, `per_party_bootstrap_v1/` | matching decomposition/bootstrap modules | t09–t12/t22; Appendix a18; `fig8_reform_party_split.png` (Figure 5) |
| §5.5 seat calls | `unblinding_2026_v1/` | `unblind_2026.py` | t07/t08; Appendix a4; `fig2_seat_totals.png` |
| §5.6 transfer | `woking_south_blind_v1/`, `haslemere_probe/` | `woking_south_*.py`, `haslemere_probe_prediction.py` | t14/t15/t20/t21; Appendix a10 (a6/a9 are component tables, not separately included by `report.tex`) |
| §6.3 training design | `byelection_enrichment_v1/` | `byelection_enrichment.py` | reliability figures in §6.3 |
| pack-only: design resolution | `minimal_detectable_effect_v1/` | `minimal_detectable_effect.py` | t23, a7 (not cited in the final report text) |
| appendix tables | t01–t23 plus named frozen evidence | `report_appendix_tables.py` | `outputs/report_tables_v1/latex/`; `report.tex` currently includes 14 of these files, including a15/a17/a18 regenerated directly from their frozen JSON evidence |

## How to trace any number (worked example)

Report §5.1 says news MAE 4.2051 at 31–90 days. The trail:

1. **Table pack**: `outputs/report_tables_v1/t05_confirmatory_v2.csv`,
   row combined/90-31 days — written by
   `build_report_tables.py::t05_confirmatory_v2()`.
2. **Frozen artefact**: that builder reads
   `news_features/unblinding_2026_v1/unblinding_results.json`, whose
   sha256 is pinned in `outputs/report_tables_v1/manifest.json`.
3. **Computation**: the JSON was written once by
   `src/news_modelling/unblind_2026.py` (integrity checks, then
   `score_specification()` / `_bootstrap_rows()` for the deltas and
   contest-bootstrap CIs) scoring the frozen predictions in
   `news_features/blinded_2026_predictions_v2/` against observed
   results.
4. **Guards**: the relevant `tests/` modules plus build-time assertions in the
   table pack, the appendix builder and `demo/build_viva_pack.py`.

The same four steps work for every table: find the tXX CSV, read
`manifest.json` for its input, open the producing module named above.
The viva pack (`demo/viva_pack.html`, section 9) embeds all of this
clickably.

## Local-by-design artefacts (OneDrive copies, git-ignored)

Per the IRP large-file rule, large or copyright-sensitive boundaries stay off
Git. Some are regenerable outputs; frozen historical/API/LLM evidence must
instead be restored and verified against committed hashes. Copies are stored
in the OneDrive folder
[`irp-sl1425-large-files`](https://imperiallondon-my.sharepoint.com/:f:/g/personal/sl1425_ic_ac_uk/IgBi8ECozK1UT6t7z3t8-CRpASvOBLyw6FIXgyId6DA35TY?e=Drejw9);
the item-by-item restore instructions are in the README's
"Large local artefacts" table.

| artefact | size | regenerate |
| --- | --- | --- |
| `data/` (uploaded as three tar.gz batches + the PDF folder + the sidecar archive) | large raw boundary | restore the frozen inputs; collection code rebuilds downstream records but does not recreate every original source byte |
| `news_features/blinded_2026_predictions_v1/blinded_predictions.csv` | ~20 MB | historical frozen prediction bytes; sha256 manifest committed beside it |
| `news_features/blinded_2026_predictions_v2/blinded_predictions.csv` | ~10 MB | historical frozen prediction bytes; sha256 manifest committed beside it |
| `llm_context/d4_llm_outputs*.json` | ~3 MB | frozen raw LLM responses (copyright-excluded); verified by `d4_llm_output_manifest.json` |
| `llm_context/corpus_extraction_outputs_*.json` (nine tranches) | ~16 MB | local raw extraction outputs required to rebuild the corresponding feature releases; committed digests/manifests carry verification evidence |
| `surrey-election-no-news-baseline/outputs/model_bundle_v1/` | 15 MB | Stage 1 subproject workflow |

`Supervisor Requirement/` is local-only by supervisor instruction and is
neither tracked nor mirrored.

## Generated files (never committed)

Disposable caches such as `__pycache__/` and generated convenience outputs such
as `demo/viva_pack.html` can be rebuilt. Do not treat every ignored file as
disposable: the frozen and copyright-sensitive artefacts listed above may need
restoration from OneDrive and hash verification rather than regeneration.
