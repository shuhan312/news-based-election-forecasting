# Missing News Representation Audit

Phase 7, Step 7. Version `missing-news-v1.0-2026-07-27`.

## 1. Expected grid construction

Generated from the official election tables (81/81/91/81
wards/divisions across the four elections, with each ward carrying
only the registry parties that actually contested it), crossed with
12 windows (6 individual + 6 cumulative, keyed by `window_type`) and
5 news scopes, plus one `ELECTION_WIDE` target per election carrying
every party that contested plus Reform UK as a tracked
emerging-party comparison. Invalid combinations are materialised as
`not_applicable`. Step 5 groups that fall outside the construction
(chiefly `(no_focal_party)` cells) are appended as
`observed_extension` so reconciliation is exact. Full rules in
`missing_news_methodology.md`.

**90,974 cells x 33 columns** (90,600 expected-grid, 374
observed-extension).

## 2. Files created or modified

Created: `missing_news_representation.parquet` (64K, in Git),
`missing_news_representation.csv` (28M - created as required but
gitignored under the large-file policy; the parquet is identical
content and regenerates in seconds), `missing_news_methodology.md`,
this audit, `missing_news_error_analysis.md`, plus
`src/news_features/missing_news.py`,
`src/news_features/run_missing_news.py` and
`tests/test_missing_news.py`. **No previous output was modified** -
the runner asserts the Step 5 CSV bytes and the Step 6 parquet hash
are unchanged after every build.

## 3. Counts by missing-news state

| state | cells | share |
|---|---|---|
| insufficient_search_coverage | 48,231 | 53.0% |
| not_applicable | 34,800 | 38.3% |
| source_unavailable | 3,732 | 4.1% |
| pending_external_stage | 3,667 | 4.0% |
| observed_news | 544 | 0.6% |
| unresolved_processing | 0 | 0% (absorbed by higher precedence) |
| **confirmed_zero_news** | **0** | **0%** |

Secondary indicators (set independently of the winning state, so
nothing is lost to precedence): unresolved_processing 56,174;
pending_stage 56,174; insufficient_coverage 48,557;
source_unavailable 3,782. Of the 544 observed cells, 326 also carry
an insufficient-coverage flag and 50 a source-unavailable flag -
i.e. even where news was observed, the coverage behind it is known
to be partial.

`coverage_confidence` over the 56,174 assessable cells: 0.556 for
52,339 cells and 0.667 for 3,835 cells (mean 0.563). No cell reaches
1.0, which is why no zero is confirmed.

## 4. Local and national coverage findings

The headline finding of this step: **ward-tier search was executed
for only 7.2% of ward cells** (13 wards per election out of 81-91;
Stages C and M sampled the same 13). The remaining ~68-78 divisions
per election were never searched at ward level, so 48,231 ward cells
are `insufficient_search_coverage` - they carry no information about
whether local news existed, and treating them as zero would have
been the single largest error available in this pipeline.

Election-wide coverage is materially better: national, mixed,
surrey-wide and regional scopes at election level are
`pending_external_stage` (searched adequately; awaiting Stage M
ingestion), never `insufficient_search_coverage`. Local and national
states therefore differ per election exactly as the specification
requires, and national adequacy is never allowed to stand in for the
missing ward-tier searches (tested).

## 5. Stage M pending records

Stage M executed all 810 queries and wrote 2,667 records not yet
ingested: ESWS-2026 571, SCC-2013 610, SCC-2017 747, SCC-2021 739.
Every assessable cell of every election consequently carries
`pending_stage_indicator = 1`, and `zero_news_indicator = 0` is
guaranteed while that holds (tested). Re-execution after ingestion
recomputes the states deterministically without a code change.

## 6. Confirmed-zero evidence

**No cell qualifies.** Three independent blockers hold across the
whole grid: Stage M records are not ingested; eligibility decisions
remain unresolved (SCC-2013 52, SCC-2017 41, SCC-2021 40, ESWS-2026
28); and the LLM extraction layer covers only the 67-article pilot
rather than the 1,542 canonical articles. This is the correct and
intended outcome at the current pipeline state - the layer exists
precisely to stop an unverifiable zero being asserted, and it will
begin confirming zeros once those three blockers clear.

## 7. Unresolved risks

Detailed in `missing_news_error_analysis.md`: the ward-tier search
gap is a design-level limitation of the collection protocol rather
than a processing backlog; `unresolved_processing` is currently
unobservable as a primary state because Stage M outranks it
everywhere; and grid size grows with the ward roster, so the full
grid is distributed as parquet.

## 8. Test results

17 new tests in `tests/test_missing_news.py` - **17 passed**.
Full repository suite: **584 passed, 0 failed**.
