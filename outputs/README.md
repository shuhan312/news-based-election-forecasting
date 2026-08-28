# `outputs/` — generated products and audit records

This directory contains downstream products. It is not a raw-data source, but
not every item has the same role: report packs are generated presentation
artefacts, machine-readable audit ledgers record a verified repository state,
and bulky working files remain local.

## The report pack (Layer 7) — committed and hash-pinned

### Tables

`report_tables_v1/` contains:

- 23 machine-readable tables (`t01`–`t23`) written by
  `news_modelling.build_report_tables`;
- `manifest.json`, which pins every input read by that table-pack builder;
- the generated LaTeX directory used directly by `report/report.tex`.

`news_modelling.report_appendix_tables` formats the pack plus explicitly named
frozen evidence into the LaTeX tables. The report includes 14 of those files;
the other LaTeX tables are component or pack-only views. There are no duplicate
`a*.tex` copies under `report/`. See
[`report_tables_v1/README.md`](report_tables_v1/README.md).

### Figures

`report_figures_v1/` contains 10 generated figures. They are produced by
several modules, not one:

- `make_report_figures.py` writes the six core analysis figures;
- `study_design_figure.py`, `corpus_funnel_figure.py` and
  `framework_figure.py` write three structural figures;
- `reform_party_split_figure.py` writes the Reform split figure.

The written report reads committed report-facing copies from `report/figures/`.
It uses five figures represented in this pack plus the pipeline overview built
under `news_features/pipeline_overview_v1/`; the remaining pack figures are
supplementary. The exact six-file mapping is in
[`../REPRODUCIBILITY.md`](../REPRODUCIBILITY.md).

Build-time assertions and table-regeneration tests fail on numerical or
presentation drift. See [`../REPO_MAP.md`](../REPO_MAP.md) for the complete
report-section → artefact → code trace.

## Committed audits and retained evidence

The directory also holds small committed outputs whose value is the recorded
verdict or project evidence, including the leakage/provenance JSON and CSV.
These are not report-pack inputs merely because they live under `outputs/`;
their producing command and authority are documented beside them or in the
root reproducibility guide.

## Research workbooks and labelling queues — local, regenerable

Other directories may be bulky working artefacts — the combined research
workbook, the master and news workbooks, the D4 and manual labelling queues, the
window-scheme comparison and the progress deck. Per the IRP large-file rule they
are **git-ignored** and kept on OneDrive; the code that builds each one is
tracked (see `scripts/` and `src/`), so they regenerate on demand. The one
committed narrative here is `IRP_Surrey_Election_Experiment_Log_*.md`.

## Rule

Commit a generated output only when it is a report dependency, a compact
machine-readable audit verdict, or explicitly retained final evidence. Keep
bulky convenience outputs local. A file's authority comes from its documented
producer, inputs and hashes—not from the fact that it lives under `outputs/`.
