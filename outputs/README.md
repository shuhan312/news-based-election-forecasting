# `outputs/` — generated products

Everything here is regenerated from versioned code and the frozen evidence; none
of it is a source input. It holds two very different kinds of product.

## The report pack (Layer 7) — committed and hash-pinned

The only outputs the written report reads:

- `report_tables_v1/` — the 23 report tables (`t01`–`t23`) plus the LaTeX
  appendix tables in `latex/`, built by `src/.../build_report_tables.py` and
  `report_appendix_tables.py`. Its `manifest.json` pins the `sha256` of every
  frozen input, so each table traces to the exact artefact it was built from.
  This directory has its own [`report_tables_v1/README.md`](report_tables_v1/README.md).
- `report_figures_v1/` — the 9 report figures, built by `make_report_figures.py`.

These are small, committed, and are the layer the report, the Streamlit app and
the viva pack all read. Build-time assertions fail if a number drifts from its
frozen source. See [`../REPO_MAP.md`](../REPO_MAP.md) for the
report-section → artefact → code trace.

## Research workbooks and labelling queues — local, regenerable

The remaining directories are bulky working artefacts — the combined research
workbook, the master and news workbooks, the D4 and manual labelling queues, the
window-scheme comparison and the progress deck. Per the IRP large-file rule they
are **git-ignored** and kept on OneDrive; the code that builds each one is
tracked (see `scripts/` and `src/`), so they regenerate on demand. The one
committed narrative here is `IRP_Surrey_Election_Experiment_Log_*.md`.

## Rule

Only the report pack is committed, because only it is read by the report and must
be verifiable. Anything else under `outputs/` is a regenerable convenience copy
and is reproduced from tracked code, never treated as a source of truth.
