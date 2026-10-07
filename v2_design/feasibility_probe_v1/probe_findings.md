# Multi-council feasibility probe: findings

**2026-10-07.** The criteria were committed first (`criteria.md`, commit
9eba664). Outputs: `results_availability.json`, `news_coverage.json`. No vote
count, winner or post-window article was read.

## Verdict

- **Election data: GO.** Kent is complete, structured and free. Moving to
  another council means changing an election id.
- **News: NOT DETERMINED by this probe.** Both pre-registered news measures
  turned out invalid (amendment A1). What the probe did establish is
  negative and useful: dated Google search is not a viable collection route
  for local news, for Kent *or* for Surrey.

## Election data (R1–R3)

| | Kent 2017 | Kent 2021 | Kent 2025 |
|---|---:|---:|---:|
| divisions | 72 | 71 | 72 |
| candidacies | 393 | 343 | 427 |
| R1 candidate list present | 100% | 100% | 100% |
| R2 result record present (presence only) | 100% | 100% | 100% |

R3: from 2017 to 2021 Democracy Club changed the id scheme (`KEN:` → `gss:`).
All 71 division slugs match, so boundaries did not change. An id-only
comparison would have reported a full redraw, and the same trap applies to
any other council. From 2021 to 2025, 12 of 72 divisions carry new GSS codes.
Those boundaries were altered and need notional prior results.

## News (N1, N2, C1)

Identical query templates were run on all four elections (21 queries,
window 90–31 days):

| | Surrey 2021 (calibration) | Kent 2017 | Kent 2021 | Kent 2025 |
|---|---:|---:|---:|---:|
| unique URLs | 131 | 135 | 136 | 109 |
| "local" by exclusion (pre-registered N1) | 67 | 93 | 68 | 26 |
| N1 ratio, as pre-registered | — | 1.39 | 1.02 | 0.39 |
| **news-publisher URLs (N1′)** | **5** | **14** | **13** | **7** |
| of which about the county election or parties | ~0 | ~2 | ~3 | ~6 |
| N2 Wayback captures, ratio (invalid) | — | 0.14 | 0.34 | 1.30 |

C1: V1 ran ~447 local-arm dated searches per principal election. At Serper's
per-query price that is under £1 per council-election. **Pass, but cheap
does not mean useful:** about 5–10% of hits are news, and fewer still are
about the election.

## What this means for V2

1. **The data constraint is news, not results.** The bottleneck sits exactly
   where reading V1's code suggested.
2. **Generic search engines will not scale local news.** V1's 188 local
   articles came mainly from the outlet-first Wayback route plus heavy
   manual review, not from search.
3. **Kent's local press exists and is archived at least as well as
   Surrey's.** The probe surfaced KentOnline, KentLive, BBC Kent, ITV
   Meridian, Isle of Thanet News and several hyperlocals. Kent is not worse
   than Surrey. The route is what failed.
4. **Two tasks are on the critical path, in this order:**
   (a) an outlet-first retrieval probe, validated against V1's known Surrey
   2021 local corpus before it is applied to Kent; and
   (b) automated local relevance screening (N3), because outlet-first
   retrieval returns everything the outlet published.

## Caveats

- 21 queries per election is a small probe. Absolute counts are indicative.
- The judgement of which hits are "about the election" was made by reading
  titles. It is approximate and is not used for any decision.
