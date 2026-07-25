# Near-duplicate detection - Step 3 summary (v1 provisional)

* rules: `near-dup-v1.0-2026-07-26`
* articles participating: 1540 (usable text only)
* candidate pairs scored: **296**
* classifications: {'not_near_duplicate': 241, 'probable_near_duplicate': 3, 'same_event_independent_reporting': 37, 'manual_review': 12, 'high_confidence_near_duplicate': 3}
* provisional clusters: 6
* flags: {'same_url_group': 3}
* review queue: 12 rows

Classification rests on shared word sequences only - shared topics, names, places and dates never constitute duplicate evidence. Cross-publisher high-overlap pairs carry the possible_syndication_candidate flag for Step 4; nothing here is a final verdict and no record was deleted or merged.

## Review resolutions (2026-07-26)

All 12 grey-zone pairs resolved not_near_duplicate: five Guardian pairs are running-story follow-ups (recycled background, distinct developments), seven Guildford Dragon pairs share residual site furniture rather than article text. The Dragon finding is a real Step 2 gap - its WordPress theme has no standard article container, so the generic fallback kept navigation and footer lines - logged as cleaning-rules v1.1 work for the v2 layer release alongside the Stage M tranche.
