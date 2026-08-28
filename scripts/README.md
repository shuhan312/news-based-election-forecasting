# `scripts/` — retained cross-cutting utility

Repository-root helpers belong here only when they cross pipeline-layer
boundaries and preserve a final manual-review input. Production runners live in
`src/` or one of the two subprojects; report artefacts are built by
`src/news_modelling/`.

| Script | What it does |
| --- | --- |
| `update_e5_geographic_review_workbook.mjs` | Rebuilds the E5 geographic-review workbook while preserving the captured manual decisions |

## Rule

This script supports the provenance of a human-review input; it is not a model
runner and does not generate a reported result. Run it from the repository root
with Node as documented in its header. Development-only collection schedulers,
overnight wrappers and window-comparison exporters are retained in Git history,
not in the final working tree.
