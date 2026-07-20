# Streamlit extractor release verification

**Verification date:** 20 July 2026

**Scope:** Surrey Election Results Extractor Streamlit application

**Result:** release checks passed

## What was verified

The application accepts either an official Surrey election index URL or one
official area-result URL, uses the provider-neutral SerpAPI adapter, validates
retrieved evidence and returns a downloadable Excel workbook. The API key is a
masked, temporary input and is not part of workflow results, audit records or
workbook interfaces.

The release includes:

- the Streamlit URL, password, targeted-search, progress and download controls;
- indexed discovery and direct-result processing;
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
346 passed in 56.01s
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

## Remaining limitations

Indexed search evidence can be incomplete, truncated or temporarily absent.
The application therefore cannot guarantee that every official field will be
available at every run. It preserves missing values, evidence conflicts and
failed areas rather than inventing replacements.

A live SerpAPI request was deliberately not included in automated verification,
because tests must not require a private credential or consume a user's quota.
The HTTP adapter, authentication failure, rate limit, timeout, retry and network
paths are covered with mocked provider responses.
