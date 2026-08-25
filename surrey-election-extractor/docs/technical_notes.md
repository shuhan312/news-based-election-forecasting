# Technical notes

Implementation detail moved out of the top-level `README.md` to keep that file
examiner-facing. Behaviour described here is unchanged; these notes record how
the extraction workflow and search adapter are implemented.

## Preflight before any indexed search

Before a live indexed-search run, the Streamlit workflow checks the official
election index and three spread-out result pages using ordinary public HTTP.
This preflight consumes no SerpAPI quota.

## Query budget policy

Each application run has one shared budget of 200 indexed search queries, and the
SerpAPI adapter has a separate ceiling of 600 HTTP attempts, including pagination
and retries. One query may therefore consume more than one HTTP attempt when
SerpAPI publishes later result pages. These limits prevent a large election or a
temporary provider failure from creating an unbounded request sequence.

The budget is spent breadth-first: for a configured principal election the
application first gives every one of the 81 result URLs its mandatory exact
query, then permits at most one complementary voting-summary query per area. This
prevents the first few divisions from consuming the allowance before the rest of
the election is processed. Targeted searches stop early only when complete,
conflict-free candidate rows reconcile to the published total votes and seat
count.

## Discovery, denominator and exact-query reuse

Every historical-election run uses indexed discovery queries and one exact-URL
query per discovered area. That exact response is reused by the extraction stage,
so an official-page failure cannot send the same exact query twice.

The configured 2013, 2017 and 2021 elections each require all 81 published
divisions. If the landing page is unavailable, the application retries the
audited official area-index URL; if Google exposes only part of a configured
principal election, the audited result-ID inventory preserves the known 81-page
denominator. The inventory supplies URLs only — every candidate value must still
come from indexed results or a normally accessible official page. A successful
SerpAPI query with no Google matches is recorded as an empty result and does not
prevent the remaining discovery queries from running.

For the configured elections, the committed official URL, name and year are used
to construct year-specific area-result searches; retrieved pages must still
publish the matching year before they are accepted.

## Pagination

For broad `mgElectionAreaResults.aspx` discovery searches, when SerpAPI
explicitly supplies a next-page URL, the adapter follows its increasing `start`
offsets, deduplicates repeated results and stops after ten pages or 100 distinct
results. Narrow per-area field searches remain single-page, and the workflow caps
follow-up extraction at one summary-focused query per area.

## ModernGov headerless row parser

A ModernGov candidate row retained without its table header is parsed only when
it contains the visible `Image` marker, a supported party phrase and numeric
votes on the exact official area-result URL.

## Wayback fallback mechanics

Wayback requests use bounded exponential-backoff retries for temporary rate-limit
and network errors (retryable HTTP statuses 429, 500, 502, 503, 504), and
resolved snapshots and page bodies are cached for the run so each archived page
is downloaded at most once. The newest usable capture is preferred, skipping any
capture that stored the challenge stub itself. After the first protection
response the live site is not contacted again during the run.

## Adding another indexed-search provider

Implement the `SearchProvider.search(query)` interface in
`election_extractor/search_providers/`, returning provider-neutral `SearchResult`
objects. Pass the adapter into `run_extraction_workflow` during testing or
application configuration. Discovery, extraction, validation, query-budget and
workbook code should not contain provider-specific response parsing.
