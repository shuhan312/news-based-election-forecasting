# Surrey Election Results Extractor

This project builds a source-preserving Surrey County Council election database
for testing whether pre-election news improves winning-party and party-vote-
share predictions beyond previous election results.

## Purpose and role in the IRP

This repository provides the reproducible data pipeline that constructs the
Surrey County Council election database used by the IRP. It supplies the
historical election data for the no-news baseline against which the project tests
whether pre-election news adds predictive information beyond previous results.
The pipeline preserves source evidence, validates extracted values and produces
audit-ready feature and target datasets for downstream modelling; model fitting
and evaluation are downstream and are not part of this repository.

## Current release summary

- 24 election events: the 2013, 2017 and 2021 principal elections, separate East
  and West Surrey 2026 elections, and 19 by-elections.
- 1,992 candidate rows and 343 division or ward rows.
- 24 reviewed 2021→2026 geographic relations and 205 approved historical
  references.
- Official values are never altered; supplementary, derived and analysis layers
  keep separate provenance and status fields, with publication gaps left visible.

The release interpretation is documented in:

- [`docs/election_data_readiness_audit.md`](docs/election_data_readiness_audit.md)
- [`docs/supervisor_field_coverage_matrix.md`](docs/supervisor_field_coverage_matrix.md)
- [`docs/historical_longitudinal_field_provenance_audit.md`](docs/historical_longitudinal_field_provenance_audit.md)
- [`docs/no_news_electoral_baseline.md`](docs/no_news_electoral_baseline.md)

## Repository structure

Logic, execution and evidence are kept separate, and every module is
independently testable.

| Location | What it holds |
| --- | --- |
| `election_extractor/` | The library: pure logic modules (discovery, extraction, validation, workbook, master database, geographic crosswalk, release contracts). |
| `scripts/` | The runners: each `generate_*.py` calls the library and writes one output or audit file. |
| `tests/` | One `test_*.py` per library module, using mocked pages so no live SerpAPI key is needed. |
| `config/` | Frozen, verified input evidence and policy as JSON; every record keeps its source URL and validation status. |
| `outputs/` | Generated products: the master database, release audits and the no-news contracts. |
| `docs/` | Release verification, readiness and provenance audits. |
| `app.py` | A thin Streamlit shell that only collects inputs and calls `run_extraction_workflow`; all rules live in the library. |

Each feature uses one naming convention — `election_extractor/X.py` (logic),
`scripts/generate_X.py` (runner) and `tests/test_X.py` (test) — so the module
prefix groups related code without nested packages.

## Data extraction workflow

`run_extraction_workflow` processes one principal-election, area-index or single
result URL in ordered stages: it validates the URL, runs a no-quota preflight
against the official index and three spread-out result pages, discovers every
area so the published denominator is fixed (each configured 2013, 2017 and 2021
election requires all 81 divisions), extracts the candidate table and voting
summary for each area, validates the records and builds the workbook. Discovery
and every exact area-result URL are audited with indexed search, but search
snippets never overwrite official rows, and missing source values are never
inferred.

For every official page the retrieval order is:

1. the live official council page (one ordinary public request);
2. the archived official copy of the same URL from the Internet Archive;
3. indexed-search evidence.

Search pagination, the query-budget policy, the ModernGov row parser and the
provider interface are documented in
[`docs/technical_notes.md`](docs/technical_notes.md).

## Streamlit application

The single-page application accepts a Surrey principal-election landing page, an
election-area index URL or one official ward/division result URL, and produces a
workbook with an Index, one worksheet per area and an Extraction Log.

Create and activate a virtual environment, then install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r surrey-election-extractor/requirements.txt
```

Run the application from the extractor directory:

```bash
cd surrey-election-extractor
streamlit run app.py
```

Enter a SerpAPI key in the masked field. The application keeps the key in memory
for the request only, clears the widget after processing, and does not write it
to project files or workbooks. No real API key is included in this repository.

Area statuses mean:

- `Complete`: all required candidate and voting-summary values are present and
  validation passes.
- `Incomplete`: an area was found, but published values are missing or a check
  requires review. Missing values remain blank and are listed in the audit.
- `Failed`: the result URL was found but no reliable election-result data could
  be extracted, or extraction/validation failed.

## Source recovery and audit strategy

The live council site is served behind Imperva Incapsula bot protection and often
returns a challenge stub instead of the published tables. When that happens the
application does **not** attempt to bypass the protection. Instead it falls back
to the lawful archived official copies held by the Internet Archive's Wayback
Machine, which stores HTTP-200 captures of the official 2013, 2017 and 2021
area-result and index pages. Only if the council page is blocked *and* no usable
archived copy exists does the application switch to indexed-only mode.

Every value served from an archived copy records its capture timestamp, the exact
`web.archive.org` snapshot URL and the extraction evidence in the field record
and the workbook's Extraction Log, so archived values stay fully auditable and
distinguishable from live retrievals. The per-area audit also retains the attempt
time, query where applicable, result counts, selected official URLs, and parsing
and validation warnings; it never retains raw provider responses or credentials.

## Output and reproducibility

An ordinary application export contains:

1. `Index` as the first worksheet, with one row and links for every discovered
   ward or division;
2. one worksheet per ward or division, containing the candidate table and the
   six-row Voting Summary;
3. `Extraction Log` as the final worksheet.

Missing numeric source values remain blank rather than being inferred.

The released datasets are rebuilt from committed local audits without downloading
election pages. This step reuses the `.venv` created in the Streamlit application
section above; create it first if it does not yet exist. Run from the repository
root (`irp-sl1425`):

```bash
PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_master_election_database.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_final_position_qa.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_final_election_data_release_audit.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_electoral_baseline.py

PYTHONPATH=surrey-election-extractor .venv/bin/python \
  surrey-election-extractor/scripts/generate_no_news_party_contests.py
```

The primary generated files are:

- `outputs/master_surrey_election_database/master_election_database_payload.json`
- `outputs/master_surrey_election_database/master_election_database_schema.md`
- `outputs/master_surrey_election_database/master_election_database_audit_summary.md`
- `outputs/final_election_data_release_audit/final_election_data_release_audit.json`
- `outputs/no_news_electoral_baseline/no_news_electoral_baseline.json`
- `outputs/no_news_party_contests/no_news_party_contest_features.json`
- `outputs/no_news_party_contests/no_news_party_contest_targets.json`

Generated workbooks and large research outputs are stored outside Git in the
university OneDrive; the code, configuration, tests and compact audit
documentation remain version controlled. The release above is reproduced offline
from the committed audits, so these workbooks are not required to rebuild it. One
representative full extraction is linked below as an example of the application's
end-to-end output.

[Representative 2017 full extraction, sample only (OneDrive)](https://imperiallondon-my.sharepoint.com/:f:/r/personal/sl1425_ic_ac_uk/Documents/IRP%20Surrey%20Election%20Extractor/2017%20Full%20Extraction?csf=1&web=1&e=DFwaAb)

## Testing

From `surrey-election-extractor/` with the project environment activated:

```bash
python -m pytest -q
```

API and application acceptance tests use mocked official pages and indexed
results; they do not require or consume a live SerpAPI key. The acceptance tests
reopen generated workbook bytes with `openpyxl` and verify the expected sheets,
values, blank cells, hyperlinks and audit structure. The final clean-environment
checks are recorded in
[`docs/streamlit_extractor_release_verification.md`](docs/streamlit_extractor_release_verification.md).

## Current limitations

- An official result page can omit a requested value. For example, the Reigate
  2017 page publishes 4,109 issued ballots and 4,109 candidate votes but no
  rejected-ballot value. The export keeps that field blank and marks the area
  Incomplete rather than writing a calculated zero.
- Indexed titles and snippets can be incomplete, truncated or temporarily absent
  even when the council page exists, and pagination cannot force Google to index
  every official result page.
- The application combines evidence only when election, area and result URL
  match; unresolved conflicts remain Incomplete rather than being guessed.
- A `Complete` status means the required published fields were retrieved and
  validated; it is not a claim that the search index is a permanent archive.
- A query or HTTP-request ceiling can stop an unusually large or repeatedly
  failing task, and the user receives a clear error instead of a partial workbook
  presented as successful.
- Archived official copies reproduce the official page as captured. If the page
  itself omitted a value, the archived copy omits it too and the area remains
  Incomplete; the fallback never fills gaps from other sources.

## Source and inference policy

Official result fields are never filled from a lower evidence layer. A derived or
analysis value is published only when its inputs, formula, scope and source are
retained. Fuzzy candidate matching, UKIP/Reform merging, unapproved boundary
transfer and vote redistribution are prohibited.

Predictors and target-election outcomes are stored separately: the no-news input
release includes the 343-row division history table and a separate 1,624-row
party-contest publication, of which 796 single-member party contests have an
approved lagged party share for the primary baseline experiment. Model fitting,
temporal evaluation and release of baseline predictions remain downstream.
