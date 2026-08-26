# `scripts/` — cross-cutting orchestration and utilities

Repository-root helper scripts that do not belong to any single pipeline layer.
The layered pipeline itself lives in `src/` (news side) and the two subprojects;
these scripts drive, export from, or assemble across those layers. They are
convenience runners — nothing here is read by the report, and their bulky outputs
are git-ignored (see `outputs/`).

| Script | What it does |
| --- | --- |
| `build_combined_research_workbook.py` | Builds the single research workbook with the fifteen tabs the brief asks for |
| `export_window_scheme_comparison.py` | Exports the three news-window schemes side by side as a workbook |
| `collect_ward_first.py` | Runs collection in value order (ward-first) rather than stage order |
| `overnight_followup.py` | Waits for a collection run, retries anything that never reached the engine, and re-measures |
| `apply_e5_ai_assisted_draft.mjs` | Prepares the E5 geographic-linkage review draft (local-article narrowing) |
| `update_e5_geographic_review_workbook.mjs` | Rebuilds the E5 geographic review workbook after manual cells are captured |

## Rule

These are operational helpers, not part of the reproducible evidence chain. The
figures the report cites come from the layered pipeline and the `outputs/`
report pack, not from anything produced only here. Run them from the repository
root with the project `.venv` active (Python scripts) or Node (`.mjs` scripts).
