# Repository map

Orientation for readers (examiner, supervisor, future self): what every
directory is for, which report content it backs, and how to trace any
reported number to the code that produced it. The repository is a
one-way pipeline — each layer reads only the layer above it, and
`tests/test_artefact_citations.py` enforces the boundary at the end.

## The pipeline, layer by layer

| layer | where | tracked files | what it does |
| --- | --- | ---: | --- |
| 1 Collection | `src/` (top level), `src/news_collection/`, `surrey-election-extractor/` | 68 + 200 | Official election results (validated against source pages) and the news corpus (SerpAPI, publisher search, web archives), with eligibility and leakage screening; every keep/drop decision recorded |
| 2 Cleaning | `src/dedup/`, `src/normalisation/` | in src count | Exact/near-duplicate handling, name and character standardisation |
| 3 LLM extraction | `src/llm_extraction/`, `llm_context/` | 85 in llm_context | Claude-based issue/stance/framing layers, the kappa >= 0.60 validation gate, freeze of accepted labels; `llm_context/` holds run outputs and decision records |
| 4 Features | `src/news_features/` | in src count | Article-level labels to election-party-window feature tables (v1/v2), leakage audits |
| 5 Modelling | `src/news_modelling/`, `surrey-election-no-news-baseline/` | 42 + 141 | Stage 1 (history-only LightGBM, its own subproject) and Stage 2 (per-window ridge on residuals), frozen blinded predictions, the one-time unblinding, all post-unblinding diagnostics |
| 6 Frozen evidence | `news_features/*_v1//probe dirs` (24 artefact families), `news_protocol/` | 71 + 20 | The home of every reported fact: one directory per experiment (results JSON + findings.md), register-numbered; protocols and pre-registrations |
| 7 Report pack | `outputs/report_tables_v1/` (23 CSVs + manifest + latex a1–a19), `outputs/report_figures_v1/` (10 figures) | 60 | Built by `build_report_tables.py` / `make_report_figures.py` / `report_appendix_tables.py` from layer 6, with build-time assertions; `manifest.json` pins the sha256 of every input |
| 8 Consumers | `report/` (LaTeX), `app/` (Streamlit), `demo/` (viva pack) | 14 + 1 + 4 | Read layer 7 only; the tests fail if they cite anything uncommitted |

Supporting directories: `tests/` (56 modules guarding every layer),
`logbook/`, `deliverables/`, `scripts/`, `title/`, and `data/` (13 GB of
raw/processed inputs — local by design, see below).

Why there are ~1,040 tracked files: roughly 210 are pipeline code, 56
are root tests, ~380 are frozen evidence and decision records (layers
6–7 and the root evidence directories), and 341 belong to the two
subprojects. The evidence records are the point: every number in the
report has a committed, hash-pinned home.

## Report section → artefact → code

| report | frozen artefact (layer 6) | computed by (layer 5) | tables/figures |
| --- | --- | --- | --- |
| §3 data | `news_collection/canonical_corpus_release_v2.json` | collection pipeline | t17, fig0b |
| §4 Stage 1 | `surrey-election-no-news-baseline/outputs/model_bundle_v1/` (local) | Stage 1 subproject | t01–t03, a1 |
| §4 Stage 2 + freeze | `news_features/blinded_2026_predictions_v1//v2/` | `blinded_2026_predictions*.py`, `news_estimator.py` | fig0c |
| §4 LLM validation | evidence register + `llm_context/` | `src/llm_extraction/` | Table 1 / a5 |
| §5.1 confirmatory | `news_features/unblinding_2026_v1/` | `unblind_2026.py` | t04/t05, a2a/a2b, fig1 |
| §5.2 sensitivity | same | `unblind_2026.py` | t06, a3, a12 |
| pack-only: local v3 re-run | `local_v3_rerun_v1/` | `local_v3_rerun.py` | t19 (not cited in the final report text) |
| §5.3 diagnostics | `placebo_specifications_v1/`, `identity_placebos_v1/`, `stance_volume_margins_v1/` | `identity_placebos.py`, `stance_volume_margins.py` | a13 |
| §5.4 Reform | `exploratory_decompositions_v1/`, `per_party_bootstrap_v1/` | `exploratory_decompositions.py`, `per_party_bootstrap.py` | t09–t12, t22, fig4/fig6 |
| §5.5 seat calls | `unblinding_2026_v1/` | `unblind_2026.py` | t07/t08, a4, fig2 |
| §5.6 transfer | `woking_south_blind_v1/`, `haslemere_probe/` | `woking_south_*.py`, `haslemere_probe_prediction.py` | t14/t15/t20/t21, a6, a10 |
| §6.3 training design | `byelection_enrichment_v1/` | `byelection_enrichment.py` | reliability figures in §6.3 |
| pack-only: design resolution | `minimal_detectable_effect_v1/` | `minimal_detectable_effect.py` | t23, a7 (not cited in the final report text) |
| appendix tables | (reads layer 7) | `report_appendix_tables.py` — one function per table a1–a19 | `outputs/report_tables_v1/latex/` |

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
4. **Guards**: `tests/` (56 modules) plus build-time assertions in the
   table pack, the appendix builder and `demo/build_viva_pack.py`.

The same four steps work for every table: find the tXX CSV, read
`manifest.json` for its input, open the producing module named above.
The viva pack (`demo/viva_pack.html`, section 9) embeds all of this
clickably.

## Local-by-design artefacts (OneDrive copies, git-ignored)

Per the IRP large-file rule — everything regenerates from tracked code;
integrity carried by committed sha256 manifests. Copies live in the
OneDrive folder
[`irp-sl1425-large-files`](https://imperiallondon-my.sharepoint.com/:f:/g/personal/sl1425_ic_ac_uk/IgBi8ECozK1UT6t7z3t8-CRpASvOBLyw6FIXgyId6DA35TY?e=Drejw9);
the item-by-item restore instructions are in the README's
"Large local artefacts" table.

| artefact | size | regenerate |
| --- | --- | --- |
| `data/` (uploaded as three tar.gz batches + the pdf folder + the sidecar archive) | 13 GB | collection pipelines under `src/` |
| `news_features/blinded_2026_predictions_v2/blinded_predictions.csv` | 10 MB | frozen; sha256 manifest committed beside it |
| `llm_context/d4_llm_outputs*.json` | ~3 MB | frozen raw LLM responses (copyright-excluded); verified by `d4_llm_output_manifest.json` |
| `surrey-election-no-news-baseline/outputs/model_bundle_v1/` | 15 MB | Stage 1 subproject workflow |

`Supervisor Requirement/` is local-only by supervisor instruction and is
neither tracked nor mirrored.

## Generated files (never committed)

`__pycache__/` everywhere, `demo/viva_pack.html` (rebuild:
`.venv/bin/python demo/build_viva_pack.py`), and the local artefacts
above. All covered by `.gitignore` rules; deleting them locally is
always safe.
