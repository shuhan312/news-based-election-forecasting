# Missing News Representation - Methodology

Phase 7, Step 7. Version `missing-news-v1.0-2026-07-27`.

## Why this layer exists

An empty cell in the aggregated feature table is ambiguous. It can
mean "no news was published about this party in this ward in this
window", but far more often it means "that ward was never searched",
"the archive refused the request", "those articles are collected but
not yet extracted", or "Stage M will add articles here". Passing all
of those to a model as zero teaches it that silence equals absence
of coverage. This layer makes the difference explicit and auditable,
and it refuses to certify a zero that the evidence does not support.

## Expected observation grid

The grid is generated from the official election tables, not from
the feature table:

* **election_id** - the four collected elections.
* **geographic_target_id** - one `ELECTION_WIDE` target per
  election, plus every ward/division that appears in that
  election's official results (81 / 81 / 91 / 81).
* **focal_party_id** - for a ward, exactly the registry parties that
  actually contested that ward; for an election-wide target, every
  registry party that contested the election, plus Reform UK as an
  explicitly tracked emerging-party comparison even where it did not
  stand.
* **window** - the six individual windows and the six cumulative
  windows, carried with a `window_type` key so the disjoint and
  nested readings never mix.
* **scope_classification** - the five news scopes.

Politically or structurally invalid combinations are materialised
and marked `not_applicable` rather than dropped, so the rule is
visible and testable:

* ward x `national_political` and ward x `regional` - a purely
  national or regional article is never attributed to a single ward
  (the same rule Steps 4 and 5 enforce);
* Reform UK x SCC-2013 / SCC-2017 - the party did not exist.

Groups the aggregation legitimately produced that fall outside this
construction (chiefly `(no_focal_party)` cells) are appended with
`grid_source = observed_extension`, which guarantees that every
Step 5 group reconciles into the grid.

Result: **90,974 cells** (90,600 expected-grid + 374
observed-extension).

## The seven states and their precedence

| state | meaning |
|---|---|
| `observed_news` | >= 1 eligible canonical article contributes |
| `confirmed_zero_news` | nothing contributes AND every evidence item passes |
| `insufficient_search_coverage` | the search plan never covered this cell |
| `source_unavailable` | searches ran but the source refused (4xx/429) |
| `unresolved_processing` | collected, but eligibility/duplicate/extraction incomplete |
| `pending_external_stage` | Stage M may still add articles here |
| `not_applicable` | invalid combination |

Precedence, applied top-down: `not_applicable` -> `observed_news` ->
`insufficient_search_coverage` -> `source_unavailable` ->
`pending_external_stage` -> `unresolved_processing` ->
`confirmed_zero_news`.

Two deliberate readings, recorded because they are judgement calls:

1. **Observation outranks pending.** A cell with articles is
   `observed_news` even when Stage M may add more; the
   `pending_stage_indicator` still fires, so "this value may grow"
   is preserved without pretending the observed articles do not
   exist. 544 observed cells carry a pending flag on this basis,
   and 326 of them additionally carry an insufficient-coverage flag.
2. **Search gaps outrank processing gaps.** No amount of later
   processing can create articles from a search that never ran, so
   an unsearched ward reports the search gap first. All secondary
   indicators are set regardless of which state wins, so nothing is
   collapsed away by the ordering.

## Evidence required for a confirmed zero

Nine items, all read from the collection-side records - never from
the emptiness of the feature table:

1. `search_queries_executed` - the cell's planned queries ran
   (`query_inventory.csv` vs `search_log.csv`);
2. `ward_tier_search_executed` - ward cells were searched at ward
   tier (trivially true for election-wide cells);
3. `date_range_covered` - queries span the 180-day pre-election
   window;
4. `required_sources_checked` - the arm's source set ran;
5. `no_search_failures` - no 4xx/429 among this cell's queries;
6. `external_stage_complete` - Stage M records ingested;
7. `eligibility_resolution_complete` - no pending eligibility
   decisions for the election;
8. `duplicate_resolution_complete` - Phase 5 canonical/duplicate
   layer frozen;
9. `extraction_complete` - the LLM context layer covers the
   election's canonical articles.

`coverage_confidence` is the satisfied fraction of these nine
items (None for `not_applicable`). A confirmed zero requires 9/9;
the unit tests verify that removing any single item breaks it.

## Local and national coverage rules

Scope is a grid key, so local and national coverage are assessed on
separate rows and can disagree - a ward can be
`insufficient_search_coverage` while the same election's national
scope is only `pending_external_stage`. National coverage never
substitutes for missing local-source coverage: the ward-tier
evidence item is evaluated only from ward-tier queries, and a ward
cell whose ward-tier search never ran reports
`insufficient_search_coverage` regardless of how well the national
arm was covered (tested).

## Stage M handling

Stage M's 810 queries executed and wrote 2,667 records
(571 / 610 / 747 / 739 per election), but those records are not yet
ingested into the corpus layer. Every assessable cell of every
election therefore carries `pending_stage_indicator = 1`, and no
cell can reach `confirmed_zero_news` while that holds. The runner
re-reads the collection records on every execution, so once Stage M
articles are ingested the states recompute deterministically with
no code change; the unit tests simulate both transitions
(empty+pending -> observed, and empty+complete -> confirmed zero).

## Intended treatment in later modelling

* `observed_news` - use the Step 5 / Step 6 feature values.
* `confirmed_zero_news` - a genuine zero; may enter the model as
  zero news with its own indicator.
* `insufficient_search_coverage`, `source_unavailable`,
  `unresolved_processing`, `pending_external_stage` - **not zero**.
  These are missing data: exclude from the estimation sample, or
  model them with an explicit missingness indicator. They must
  never be silently zero-filled.
* `not_applicable` - outside ordinary modelling denominators
  entirely.

No imputation is performed in this step, and the final
Ward-Party-Election table is not constructed.
