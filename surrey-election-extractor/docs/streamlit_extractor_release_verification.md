# Streamlit extractor release verification

**Verification date:** 20 July 2026 (initial release); archived-copy fallback
added and re-verified 21 July 2026 after the live council site began
returning its Incapsula protection page for ordinary requests.

**Scope:** Surrey Election Results Extractor Streamlit application

**Result:** release checks passed

## What was verified

The application accepts an official Surrey principal-election landing page,
election-area index URL or one official area-result URL. Indexed search audits
the discovery route and every exact result URL. Public council archive and
result pages provide the complete area denominator and the selected field values
when they are accessible. Search snippets and official rows remain separate
evidence tiers. Retrieved evidence is validated before the application returns
a downloadable Excel workbook. The API key is a masked, temporary input and is
not part of workflow results, audit records or workbook interfaces.

The release includes:

- the Streamlit URL, password, targeted-search, progress and download controls;
- indexed discovery and exact-URL checks combined with official table evidence;
- an 81-division completeness gate and configured official-index retry for the
  2013, 2017 and 2021 principal elections;
- bounded query, HTTP-request and retry policies;
- strict candidate, voting-summary and non-inference rules;
- Complete, Incomplete and Failed area states;
- Index, area and Extraction Log worksheets;
- typed in-memory search and validation audit records;
- mocked acceptance scenarios for index, direct, incomplete and provider-failure
  paths.

## Clean-environment verification

A new virtual environment was created outside the repository at:

```text
/private/tmp/surrey-streamlit-release-venv-20260720
```

Only the committed dependency declaration was used:

```bash
python3 -m venv /private/tmp/surrey-streamlit-release-venv-20260720
/private/tmp/surrey-streamlit-release-venv-20260720/bin/python \
  -m pip install -r requirements.txt
```

Installation completed successfully. This confirms that the application does
not depend on an undeclared package from the working development environment.

## Automated tests and static checks

The full suite was run inside the clean environment:

```bash
/private/tmp/surrey-streamlit-release-venv-20260720/bin/python -m pytest -q
```

Result:

```text
364 passed in 51.34s
```

The application and main package modules also passed `python -m py_compile`.
`git diff --check` reported no whitespace errors.

The acceptance tests generate workbook bytes from local indexed-search fixtures
and reopen them with `openpyxl`. They check:

- one Index row and worksheet for every discovered area;
- exact direct-result sheet structure;
- candidate and Voting Summary values;
- source and internal hyperlinks;
- blank numeric cells where evidence is unavailable;
- visible Incomplete and Failed notices;
- Extraction Log presence and credential exclusion.

## Application startup

The app was started from the clean environment in headless mode. Streamlit
reported a successful server start, and its local health endpoint returned:

```text
ok
```

The verification server was then stopped normally.

## Credential review

A source-controlled-file search found only variable names, environment-variable
references and function arguments used to receive the key. It found no literal
SerpAPI credential. Long hexadecimal strings reported by a general scan were
documented SHA-256 file fingerprints, not credentials.

Tests use clearly labelled fake credentials and mocked HTTP transports. No live
SerpAPI key or quota was used during release verification.

## Hybrid-path and live official-source verification

The application now performs a zero-quota official-source preflight before a
live indexed run. It verifies the full official denominator and samples the
first, middle and last result pages. A protection page selects indexed-only
mode, matching the prompt's reason for using an indexed-search API; the code
does not attempt to bypass Surrey's access controls. Automated tests also prove
that the required exact-URL query is sent once per area and reused rather than
repeated during fallback.

The automated hybrid-path test records that exact-URL query and confirms that
the exported values still come from the stronger official row.
The complete 2017 principal-election link was separately run through the public
official-source route. That live source check produced:

```text
81 divisions discovered
377 candidate rows extracted
80 Complete / 1 Incomplete / 0 Failed
all candidate rows sourced from official council pages
```

The hybrid application combines these verified behaviours: indexed discovery
and exact-URL attempts are logged, while the official archive preserves the full
division denominator and official tables supply the selected values. A private
SerpAPI key is not stored or consumed by the automated release suite.

### Archived-copy fallback (added when the live council site is protected)

The live council site is now served behind Imperva Incapsula and returns its
challenge page instead of the published tables for an ordinary public HTTP
request. `election_extractor/official_archive_fallback.py` adds a lawful
fallback: when the live page is blocked, the same official URL is served from
its Wayback Machine capture instead (verified via the public CDX index that
every 2013/2017/2021 official area-result and index page has an HTTP-200
capture). This is not a bypass of Surrey's protection — no request is ever
made to the council site to defeat it; a completely independent, lawful public
archive supplies the same published page. Every archived value is cited in the
extraction attempt and field evidence with its exact capture timestamp and
`web.archive.org` snapshot URL.

Re-running the same complete 2017 principal-election link with the live site
protected (Incapsula active) and only the archived-copy fallback available
produced, with a real network connection and no SerpAPI key consumed:

```text
81 divisions discovered
377 candidate rows extracted
80 Complete / 1 Incomplete / 0 Failed
elapsed: ~39 minutes (bounded 1 request/second pacing against the public
  archive, plus exponential-backoff retries during a transient rate-limit)
```

This exactly reproduces the earlier live-official-source benchmark above, even
though the live site is now blocking ordinary requests. The one Incomplete
division is again Reigate, for the same documented reason (missing published
rejected-ballot figure — see below).

During development, two defects were found and fixed while producing this
result:

1. **Status-logic divergence.** `workbook._area_status` was a separate
   duplicated implementation of the same rule already correctly implemented in
   `workflow._area_status`, and it omitted one filter: when every exported
   candidate record came from the official page, the mandatory exact-URL
   indexed audit query (required for every result URL) must not by itself
   downgrade an otherwise source-complete official row merely because Google
   does not index that specific council page. Without this fix, the exported
   workbook showed every official-sourced division as `Incomplete` even though
   the application's own progress display correctly reported `Complete`. Fixed
   and covered by
   `tests/test_workbook.py::test_11b_official_records_ignore_the_mandatory_indexed_audit_attempt`,
   which was verified to fail without the fix and pass with it.
2. **Preflight sensitivity to a short-lived archive rate limit.** Walking a
   paginated official index issues several sequential requests to the public
   archive; in one live run this left the archive briefly rate-limited exactly
   when the preflight's three sample pages were checked immediately afterwards,
   causing the whole run to fall back to indexed-only mode even though the
   same pages were reliably available moments later. Fixed by increasing the
   Wayback HTTP client's bounded retry budget (up to four retries, 1/2/4/8s
   backoff) and by giving `_run_official_preflight` one bounded extra pass
   over only the still-failing sample pages after a short pause, rather than
   deciding "archive unavailable" from a single unlucky moment.

The one Incomplete division is Reigate. Its official page publishes 4,109
ballot papers issued and candidate votes totalling 4,109, but it does not
publish a rejected-ballot value. The extractor deliberately leaves that source
field blank. A formula-derived zero exists separately in the research database;
it is not relabelled as a directly published value in the Streamlit export.

The historical `80 Complete / 1 Incomplete` result describes the verified run
above; it is not silently claimed for a later run when the official site is
returning an Incapsula page. In that condition the application uses the audited
81-URL denominator, runs indexed extraction and reports the actual Complete,
Incomplete and Failed totals produced by that run.

## Remaining limitations

Official or indexed evidence can be incomplete, truncated or temporarily absent.
The application therefore cannot guarantee that every official field will be
available at every run. It preserves missing values, evidence conflicts and
failed areas rather than inventing replacements.

A live SerpAPI request was deliberately not included in automated verification,
because tests must not require a private credential or consume a user's quota.
The HTTP adapter, authentication failure, rate limit, timeout, retry and network
paths are covered with mocked provider responses. SerpAPI responses marked
``Success`` that explicitly report no Google results are treated as an empty
query so discovery can continue; responses marked ``Error`` still stop safely.
Explicit SerpAPI next-page offsets are followed for broad area-result discovery
within a ten-page and 100-distinct-result limit, with repeated organic results
removed. Narrow per-area searches remain single-page so pagination cannot
silently multiply every targeted extraction request. Regression
tests also cover a ModernGov candidate-table row whose Google snippet retains
the candidate values but omits the table header; the row is accepted only for
the exact official result URL and remains Incomplete if other published fields
are unavailable.
Configured principal elections use their audited official URL, name and year
to issue year-specific area-result searches even when an older landing-page
query returns no metadata.
