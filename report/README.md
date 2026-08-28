# Final report source

`report.tex` is the authoritative source of the final report. Its 16 included
LaTeX tables are kept in this directory so the submitted Overleaf source is
self-contained; `make -C report sync-tables` refreshes them from the
authoritative generated copies in `../outputs/report_tables_v1/latex/`.
The six report-facing figures live in `figures/`.

Build the PDF from the repository root with:

```bash
make -C report sync-tables
make -C report
```

This writes `report/report.pdf`, which is a local build product and is not
tracked. The submitted copy belongs at
`deliverables/sl1425-final-report.pdf`, following the repository's deliverable
naming rule. The full table, figure and input rebuild order is documented in
`../REPRODUCIBILITY.md`.

## Source history

The report was drafted in the Overleaf project `Final Report` from early August
2026. The two screenshots in this directory preserve the Overleaf history panel
as of 16 August 2026. Labelled Overleaf milestones were imported into Git in
chronological order; their commit messages record the corresponding label and
date. Since 16 August 2026, `report.tex` has been maintained directly in this
repository, and Git is the version history for the final source.
