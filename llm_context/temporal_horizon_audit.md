# Temporal horizon - audit (Phase 6 Step 9)

Deterministic half `temporal-windows-v1.0-2026-07-27` (pure date
arithmetic, no LLM) | LLM half: contract `temporal-v1.0-2026-07-27`,
prompt v1.0, rules v1.0 | model `claude-sonnet-5` | batch
`msgbatch_01LmPdMaYHJZWL9jSwZkJ2aH`, 67 articles, ~$0.8. Raw
outputs: `temporal_horizon_outputs.json` +
`temporal_windows_deterministic.json` (out of Git).

## Dataset

The same 67-article pilot sample (ids, membership and provenance
preserved from `llm_context_pilot_sample_v1.csv`).

## Separation of publication timing from impact horizon

The specification's core demand, enforced by construction: windows
are computed in code from the validated effective date and the
protocol polling days; the LLM is NEVER SHOWN the publication date
(the user message contains ids, title and body only). The pilot
verifies the separation empirically: within single publication
windows the extracted horizons vary freely (the 7-to-4-day window
contains both an immediate and a long_term article; the 180-to-91
window spans mixed, long_term and uncertain) - publication distance
did not dictate the content judgement.

## Deterministic windows (67/67 assigned)

180_to_91: 47 | 90_to_31: 11 | 7_to_4: 3 | final_72_hours: 2 |
14_to_8: 2 | 30_to_15: 2. Boundary dates (d = 3/4, 7/8, 14/15,
30/31, 90/91, 180) each carry an explicit test. Leakage: zero
post-voting publications (cross-confirming the upstream eligibility
gate), zero unresolved dates, and 6 articles flagged
contains_election_result (sourced from the pilot leakage layer,
provenance recorded) - visible, never silently included.
Hours-before-polling is recorded as a date-precision lower bound,
never a fabricated clock time.

## LLM impact horizon (operational definitions)

immediate = days; short_term = weeks; medium_term = months;
long_term = beyond the electoral cycle / structural; mixed =
distinct components at different horizons; uncertain = the article
does not support a judgement. Distribution over 59 valid records:
mixed 28, long_term 19, medium_term 4, uncertain 4, immediate 3,
short_term 1 - the pilot corpus reads as structurally-persistent
politics rather than ephemeral shocks, consistent with its blame
and incumbency-risk profile from Steps 6-7.

## Mechanism and continuing stories

continuing_story: yes 52 / uncertain 5 / no 2 - the sample is
dominated by running stories, matching the dedup phase's
running-story findings. Persistence: structural 26, continuing 23,
one_off 4; decay: gradual 31, persistent 20, rapid 4. Story types
span the full vocabulary (developing_controversy 17,
long_running_issue 14, sustained_national_trend 13...).

## Reform UK temporal characters

continuing_national_momentum 10, short_lived_publicity 4,
long_term_challenger_emergence 3,
sustained_local_campaign_development 2 - the four-way distinction
the specification asks for is populated and evidence-gated (zero H4
violations).

## Evidence, uncertainty and review

Every definite horizon carries a verbatim-matched quote (H3); the 4
uncertain horizons legitimately omit evidence - uncertainty as the
honest default, not an evidence shortcut. Confidence mean 0.586;
19 records review-flagged. Caught errors: 9 lines across 8 articles
(see error analysis) - all quarantined.

## Verdict

Windows are deterministic and boundary-exact; horizons are content-
grounded and demonstrably independent of publication distance;
leakage is visible; uncertainty is preserved. The temporal layer
passes pilot validation. No prediction or embedding stages were
started.
