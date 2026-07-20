# Streamlit extractor release verification

**Verification date:** 20 July 2026

**Scope:** Surrey Election Results Extractor Streamlit application

**Result:** release checks passed

## What was verified

The application accepts an official Surrey principal-election landing page,
election-area index URL or one official area-result URL. It first reads ordinary
public council archive and result pages, then uses the provider-neutral SerpAPI
adapter only as a fallback when official access is unavailable or a page cannot
yield reliable candidate rows. Retrieved evidence is validated before the application
returns a downloadable Excel workbook. The API key is a masked, temporary input
and is not part of workflow results, audit records or workbook interfaces.

The release includes:

- the Streamlit URL, password, targeted-search, progress and download controls;
- official-first discovery and direct-result processing with indexed fallback;
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
363 passed in 54.41s
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

## Live official-source verification

The complete 2017 principal-election link was run through the official-first
workflow using a provider fixture that would fail if an indexed query were sent.
The result was:

```text
81 divisions discovered
377 candidate rows extracted
80 Complete / 1 Incomplete / 0 Failed
0 indexed-search queries
all candidate rows sourced from official council pages
```

The one Incomplete division is Reigate. Its official page publishes 4,109
ballot papers issued and candidate votes totalling 4,109, but it does not
publish a rejected-ballot value. The extractor deliberately leaves that source
field blank. A formula-derived zero exists separately in the research database;
it is not relabelled as a directly published value in the Streamlit export.

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
