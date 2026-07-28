# Missing News Representation - Error Analysis

Phase 7, Step 7. Companion to `missing_news_audit.md`: the risks
this layer surfaces, and what each one does or does not license.

## 1. The ward-tier search gap is a protocol limitation, not a backlog

48,231 ward cells (53% of the grid) are
`insufficient_search_coverage` because ward-tier searching covered
13 divisions per election out of 81-91. This does not clear when
Stage M is ingested: Stages C and M sampled the *same* 13 wards, so
ingesting Stage M raises article counts in already-searched wards
but leaves the unsearched ~68-78 divisions exactly as uninformed as
they are now.

Consequences the modelling stage must accept:

* ward-level news features will exist for a **sampled minority** of
  divisions, and the sample was drawn by the collection protocol,
  not at random with respect to news volume;
* any ward-level comparison is conditional on that sample, and the
  write-up must say so;
* the honest alternatives are to model at borough/county level
  (where coverage is adequate), to restrict ward analysis to the
  searched divisions with the sampling stated, or to extend
  ward-tier searching. That is a research-design decision, recorded
  here rather than taken silently.

## 2. `unresolved_processing` is currently invisible as a primary state

Zero cells carry it as their winning state, because Stage M is
pending everywhere and outranks it. The information is not lost -
56,174 cells carry `unresolved_processing_indicator = 1` - but a
reader scanning only the primary-state column would under-count the
processing backlog. Anyone auditing processing completeness should
read the indicator, not the state. Once Stage M ingests, this state
will surface for the elections whose eligibility or extraction is
still incomplete.

## 3. Confirmed zero is currently unreachable - by design, but watch the release

No cell reaches `confirmed_zero_news`. This is correct now, but it
creates a future failure mode: when the three blockers clear
(Stage M ingested, eligibility resolved, full-corpus extraction
done), tens of thousands of cells will flip to confirmed zero *in a
single run*. Those zeros will only be trustworthy if the ward-tier
gap in section 1 has been addressed or explicitly scoped, because
the evidence checklist's `ward_tier_search_executed` item is what
stands between "we looked and found nothing" and "we never looked".
The checklist enforces this automatically - an unsearched ward can
never reach 9/9 - but the volume of the flip should be reviewed
rather than accepted silently.

## 4. Evidence items are per-election, not per-cell, for three checks

`external_stage_complete`, `eligibility_resolution_complete` and
`extraction_complete` are evaluated at election granularity because
that is the granularity at which the underlying records exist. A
cell in a well-covered ward therefore inherits its election's
processing backlog. This is conservative (it can only delay a
confirmed zero, never fabricate one), but it means
`coverage_confidence` is coarser than the six-key grid suggests -
0.556 and 0.667 are the only two values observed.

## 5. Search-failure attribution is coarse

`source_unavailable` fires for a ward cell when any query naming
that ward failed (13 HTTP 400s per election). The failures are
attributed to the ward the query names, not to the specific
date sub-range or source that failed, so a cell can be marked
unavailable when only part of its coverage was lost. Conservative in
the right direction - it withholds a zero rather than asserting one -
but it slightly over-reports unavailability (3,732 cells).

## 6. Grid growth

90,974 cells at four elections. The grid scales with wards x parties
x windows x scopes, so a fifth election or a fuller party roster
grows it roughly proportionally. The CSV is 28M and gitignored; the
parquet is 64K because the columns are highly repetitive. Any future
consumer should read the parquet.
