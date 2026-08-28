# Context to Consequence — AI-Driven News Categorisation and Event Prediction

Independent Research Project (MSc ACSE, Imperial College London).

**Research question:** does pre-election news add predictive value for
local-election vote shares beyond an adjusted history-only baseline?
Case study: the 2026 Surrey County Council elections, with particular
attention to Reform UK, a party with little electoral history.

**Design in one sentence:** Stage 1 predicts candidate vote share from
historical election data alone (LightGBM); Stage 2 models the remaining
errors with LLM-extracted news features (per-window ridge); predictions
were frozen before the 2026 results were read, and news is scored
against a recalibrated no-news control. Headline result: under the
enriched training set (v2), combined news reduced MAE from 4.445 to
4.205 percentage points in the 31–90-day window (ΔMAE +0.240,
95% CI [+0.078, +0.387]); the pre-enrichment v1 produced no
improvement in any window.

## Repository and reproduction

- **Canonical repository:** [github.com/ese-ada-lovelace-2025/irp-sl1425](https://github.com/ese-ada-lovelace-2025/irp-sl1425)
- **Reproduction guide:** [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- **Repository map:** [REPO_MAP.md](REPO_MAP.md)
- **Final report:** [deliverables/sl1425-final-report.pdf](deliverables/sl1425-final-report.pdf)

## Repository layout

The repository is a staged pipeline. Production steps follow the declared
data flow, while validation, audit and presentation code may read explicitly
named upstream artefacts. `tests/test_artefact_citations.py` guards the
machine-readable citation surfaces used by the table pack and app; it does
not claim to parse every prose citation.
Full orientation — directory purposes, report-section-to-code mapping,
and a worked "trace any number" recipe — is in
[REPO_MAP.md](REPO_MAP.md). To reproduce any figure, table or headline
number in the final report — environment, data access, rebuild order and
the per-figure/per-table script mapping — follow
[REPRODUCIBILITY.md](REPRODUCIBILITY.md).

| where | what |
| --- | --- |
| `src/` | The pipeline: election-results collection and validation (top level), `news_collection/`, `dedup/`, `normalisation/`, `llm_extraction/`, `news_features/`, `news_modelling/` |
| `surrey-election-no-news-baseline/` | Stage 1 subproject: the history-only baseline (own README) |
| `surrey-election-extractor/` | Subproject converting official results pages into structured records (own README) |
| `news_features/`, `news_collection/`, `llm_context/`, `news_protocol/` | Frozen evidence: one directory per experiment (results JSON + findings), protocols and pre-registrations, LLM run records |
| `outputs/report_tables_v1/` | The report table pack: 23 CSVs + `manifest.json` (sha256 of table-pack inputs) + generated report-facing LaTeX tables |
| `outputs/report_figures_v1/` | The report figure pack (10 figures) |
| `report/` | Self-contained LaTeX source of the final report; its 16 table copies are synchronised from `outputs/report_tables_v1/latex/` |
| `app/` | Streamlit viewing/scenario layer over the frozen artefacts |
| `demo/` | Viva demonstrator (own README); not part of the evidence chain |
| `tests/` | Tests guarding the pipeline, blinding, table regeneration and artefact citations |
| `logbook/`, `deliverables/`, `title/`, `scripts/` | Course admin and utilities |
| [`audit_leakage_provenance.py`](audit_leakage_provenance.py) | Repository-root leakage and provenance audit — see the next section |

## Verifying the no-leakage claims

One offline command re-checks the audit trail end to end: every executed
search joins to the frozen, versioned query plan; every canonical corpus
article precedes its pre-election window cut-off; no article is
double-counted across the corpus; the news feature tables contain
predictors only, with no outcome column; the Stage 1 bundle hashes, predictor
permissions and date-bounded train/test splits agree, and non-contestation
remains a separate audit record rather than a synthetic zero-vote candidate;
Reform UK is never merged with UKIP; the blinded v1/v2 prediction freezes are intact — the committed
freeze manifests, the hashes the one-time unblinding record bound at
scoring time, and the bytes on disk today must agree, with Git history
showing each freeze committed before the unblinding and untouched since;
and the 17 local search areas are a deterministic function of election
results alone — the selection script reads no news, and every
ward-targeted search in the log was executed after the sample was
committed.

```bash
python3 -m audit_leakage_provenance
```

The audit is deterministic, calls no API, mutates no research input, and
writes its machine-readable verdict to
[`outputs/leakage_provenance_audit_v1.json`](outputs/leakage_provenance_audit_v1.json)
(the committed copy is the verdict of the latest audited run). It also writes
[`outputs/provenance_audit_v1.csv`](outputs/provenance_audit_v1.csv), a compact
event ledger whose unknown outcome-release and prediction-creation timestamps
are deliberately blank rather than inferred;
`tests/test_leakage_provenance_audit.py` runs it in the test suite.

## Quick start

Requires Python 3.14 (developed on 3.14.6). The Stage 1 subproject
declares its own dependencies in
`surrey-election-no-news-baseline/requirements.txt`.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

## Reproducing the reported artefacts

Every table and figure in the report regenerates from its declared committed
or restored frozen boundary, with build-time assertions that fail on drift.
The full command list is in `REPRODUCIBILITY.md`; the compact report-pack
sequence is:

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.build_report_tables
PYTHONPATH=src .venv/bin/python -m news_modelling.report_appendix_tables
PYTHONPATH=src .venv/bin/python -m news_modelling.stage2_fitting_cells_table
make -C report sync-tables
PYTHONPATH=src .venv/bin/python -m news_modelling.make_report_figures
PYTHONPATH=src .venv/bin/python -m news_modelling.study_design_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.corpus_funnel_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.pipeline_overview_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.framework_figure
PYTHONPATH=src .venv/bin/python -m news_modelling.reform_party_split_figure
.venv/bin/python demo/build_viva_pack.py   # offline viva pack (demo/README.md)
```

The report PDF compiles from the committed repository tree and requires a TeX
distribution with `latexmk`:

```bash
make -C report       # writes report/report.pdf
```

`report/report.tex` reads 16 synchronised LaTeX table copies under `report/`,
keeping the submitted Overleaf source self-contained. Their authoritative
generated versions live in `outputs/report_tables_v1/latex/`; `make -C report
sync-tables` refreshes the copies, and tests require byte-for-byte agreement.

The Streamlit viewer over the frozen artefacts runs from the repository
root with:

```bash
.venv/bin/streamlit run app/news_app.py
```

Upstream stages (collection, extraction, features, modelling) are run
by the `run_*` modules under `src/`; each frozen artefact directory
under `news_features/` records the exact command and inputs that
produced it.

## Large local artefacts (per the IRP large-file rule)

The following large or copyright-sensitive artefacts are deliberately not
tracked. Regenerable products can be rebuilt; historical API, LLM and frozen
prediction evidence should instead be restored and checked against committed
hashes. Copies are stored in the university OneDrive folder
[`irp-sl1425-large-files`](https://imperiallondon-my.sharepoint.com/:f:/g/personal/sl1425_ic_ac_uk/IgBi8ECozK1UT6t7z3t8-CRpASvOBLyw6FIXgyId6DA35TY?e=Drejw9)
(viewable to Imperial College London account holders).

Every `.tar.gz` below was created from the repository root with relative
paths, so downloading it into the repository root and running
`tar -xzf <archive>` restores its contents to their original locations.

| OneDrive item | size | restores to / how | regenerate with |
| --- | --- | --- | --- |
| v1 `blinded_predictions.csv` | ~20 MB | place in `news_features/blinded_2026_predictions_v1/` | historical frozen prediction bytes; integrity carried by the committed manifest beside it |
| v2 `blinded_predictions.csv` | ~10 MB | place in `news_features/blinded_2026_predictions_v2/` | historical frozen prediction bytes; integrity carried by the committed manifest beside it |
| `d4_llm_outputs.json`, `d4_llm_outputs_haiku.json` | 1.3 + 1.6 MB | place in `llm_context/` | frozen raw LLM responses (contain article text, so copyright-excluded from git); verified against the committed `d4_llm_output_manifest.json` |
| `corpus_extraction_outputs_*.json` (nine tranches) | ~16 MB | place in `llm_context/` | raw extraction boundary needed to rebuild the corresponding feature releases; verify with committed batch digests/manifests |
| `model_bundle_v1/` | ~15 MB | place in `surrey-election-no-news-baseline/outputs/` | the subproject's tracked Stage 1 workflow |
| `data-batch1-small.tar.gz` | 91 MB | extract at repo root — restores `data/raw/news/{records,api_raw,quarantine}`, `data/raw/{guardian,wikipedia,newsapi,news_pilot,surrey_county_council,surrey_2026}`, `data/processed`, `data/elections` | restore/reacquire raw inputs; tracked code rebuilds downstream releases |
| `data-batch2-text.tar.gz` | 430 MB | extract at repo root — restores `data/raw/news/text/` | restore frozen article text; it is not recreated byte-for-byte by a downstream builder |
| `data-batch3-html.tar.gz` | 812 MB | extract at repo root — restores `data/raw/news/html/` | restore frozen source captures |
| `pdf/` (592 files) | 3.2 GB | download the folder into `data/raw/news/pdf/` | restore original source PDFs; routine report reproduction does not process them again |
| `excluded_sidecars_20260726.tar.gz` | 3.3 GB | place in `data/archives/` | exclusion-decision archive, kept as evidence |

`tests/test_artefact_citations.py` guards the table-pack and app citation
surfaces and the named local-by-design exceptions. The report-table tests
check all 16 included LaTeX tables, including the separately derived Stage 2
chronology table, against the self-contained copies under `report/`.

## AI acknowledgement

I used Anthropic's Claude Sonnet 5 and Claude Haiku 4.5 through the
[Anthropic API and Claude tools](https://www.anthropic.com/) and OpenAI's
[ChatGPT](https://chatgpt.com/) and [Codex](https://openai.com/codex/)
(including GPT-5.6 Sol) for targeted assistance during code development and
repository preparation. Claude Sonnet 5 and Claude Haiku 4.5 also formed part
of the declared research pipeline for issue, stance and framing
classification. Development assistance included discussing pipeline
organisation; drafting or refining selected Python and unit-test scaffolds;
reviewing Markdown documentation, JSON metadata and manifests; and supporting
debugging, reproducibility checks and leakage/provenance audits.

I determined the research questions, methodology, feature definitions,
inclusion and exclusion decisions, interpretation and conclusions. I reviewed,
adapted and tested AI-assisted suggestions before incorporating them, rejected
suggestions that were not supported by the repository evidence, and take full
responsibility for the submitted work. The final repository reflects my own
implementation decisions and understanding, and I can explain the purpose and
operation of its submitted components.

## Module housekeeping (pre-existing IRP notes)

Please familiarise yourself with and follow
[GitHub repository instructions](https://ese-msc.github.io/irp/repos/).

Deleting or modifying the pre-existing GitHub Actions workflows or the
directory structure in this repository is strictly prohibited. IRP files
"live" alongside pre-existing files.

Scheduled workflows periodically check whether `logbook/logbook.md` has been
updated recently on `main` and whether regular commits were made to the
repository (to any branch). If inactivity is detected, a warning is
raised automatically as an issue. Those issues must not be closed.
