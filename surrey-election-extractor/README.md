# Surrey Election Results Extractor

This project builds a source-preserving Surrey County Council election database
for testing whether pre-election news improves winning-party and party-vote-
share predictions beyond previous election results.

## Streamlit extraction application

The single-page application accepts a Surrey principal-election landing page,
an election-area index URL or one official ward/division result URL. The
principal-election links supplied for 2013, 2017 and 2021 are safely validated
and retained as discovery sources. The application searches both each original
landing page and its corresponding area index, because older elections may not
be indexed consistently under both URL forms. It uses indexed search evidence
because automated access to council result pages may be blocked, validates the
retrieved records, and produces an Excel workbook containing an Index, one
worksheet per area, and an Extraction Log.

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

Enter a SerpAPI key in the masked field for the current extraction. The
application keeps the key in memory for the request, clears the widget after
processing, and does not intentionally write it to project files or workbooks.
No real API key is included in this repository.

To obtain a key, create a SerpAPI account, open the account dashboard and copy
the private API key into the application's masked field. Do not add the key to
this repository, a `.env` file, a command-line argument or a shared screenshot.
The application sends it only from the backend adapter to SerpAPI for the
current extraction.

Area statuses mean:

- `Complete`: all required candidate and voting-summary values are present and
  validation passes.
- `Incomplete`: an area was found, but published values are missing or a check
  requires review. Missing values remain blank and are listed in the audit.
- `Failed`: the result URL was found but no reliable election-result data could
  be extracted, or extraction/validation failed.

Indexed snippets can be incomplete or temporarily unavailable. The application
records its search attempts and never fills missing source values by inference.
Search-provider code is isolated behind `SearchProvider`; another provider can
be added by implementing its `search` method without rewriting extraction or
Excel generation.

For each area, the in-memory audit retains the search provider, exact attempt
time, query, result counts, selected official result URLs, parsing warnings,
validation warnings and final status. It does not retain raw provider responses
or credentials. The downloadable `Extraction Log` uses the shorter column set
specified for the workbook while the typed audit remains available to tests and
future application diagnostics.

Each application run has one shared budget of 500 indexed search queries and
the SerpAPI adapter has a separate ceiling of 600 HTTP attempts, including
retries. Targeted searches stop early only when complete, conflict-free
candidate rows reconcile to the published total votes and seat count. These
limits prevent a large election or temporary provider failure from creating an
unbounded request sequence.

### Downloaded workbook

An ordinary application export contains:

1. `Index` as the first worksheet, with one row and links for every discovered
   ward or division;
2. one separate worksheet per ward or division, containing the candidate table
   and the six-row Voting Summary;
3. `Extraction Log` as the final worksheet, containing the required compact
   search audit.

A direct result URL therefore produces exactly `Index`, one area worksheet and
`Extraction Log`. Missing numeric source values remain blank. An optional
`Election Structure Metadata` worksheet is created only by research pipelines
that explicitly supply separate statutory metadata; it is not added to an
ordinary Streamlit export.

### Application limitations

- Indexed titles and snippets can be incomplete, truncated or temporarily
  absent even when the council page exists.
- Search engines can update their index after an election page changes, so the
  extraction log and source URL should be retained with every workbook.
- The application combines evidence only when election, area and result URL
  match; unresolved conflicts remain Incomplete rather than being guessed.
- A Complete status means the required published fields were retrieved and
  validated. It is not a claim that the search index is a permanent archive.
- A query or HTTP-request ceiling can stop an unusually large or repeatedly
  failing task. The user receives a clear error instead of a partial workbook
  presented as successful.

### Adding another indexed-search provider

Implement the `SearchProvider.search(query)` interface in
`election_extractor/search_providers/`, returning provider-neutral
`SearchResult` objects. Pass the adapter into `run_extraction_workflow` during
testing or application configuration. Discovery, extraction, validation,
query-budget and workbook code should not contain provider-specific response
parsing.

### Testing the application

From `surrey-election-extractor/` with the project environment activated:

```bash
python -m pytest -q
python -m py_compile \
  app.py \
  election_extractor/discovery.py \
  election_extractor/extraction.py \
  election_extractor/search_providers/serpapi.py \
  election_extractor/workflow.py \
  election_extractor/workbook.py
```

All API and application acceptance tests use mocked indexed results. They do
not require or consume a live SerpAPI key. The acceptance tests reopen generated
workbook bytes with `openpyxl` and verify the expected sheets, values, blank
cells, hyperlinks and audit structure.

The final clean-environment checks and prompt-coverage summary are recorded in
[`docs/streamlit_extractor_release_verification.md`](docs/streamlit_extractor_release_verification.md).

## Current election-data release

- 20 election events: the 2013, 2017 and 2021 principal elections, separate
  East and West Surrey 2026 elections, and all 15 configured by-elections.
- 1,971 candidate rows and 339 division or ward rows.
- Official values remain unchanged; supplementary, derived and analysis layers
  retain separate provenance and status fields.
- 24 reviewed 2021→2026 geographic relations and 201 approved historical
  references across principal elections, by-elections and 2026.
- Complete analysis vote share and derived competition rank coverage, with
  official publication gaps retained visibly.

The release interpretation is documented in:

- [`docs/election_data_readiness_audit.md`](docs/election_data_readiness_audit.md)
- [`docs/supervisor_field_coverage_matrix.md`](docs/supervisor_field_coverage_matrix.md)
- [`docs/historical_longitudinal_field_provenance_audit.md`](docs/historical_longitudinal_field_provenance_audit.md)
- [`docs/no_news_electoral_baseline.md`](docs/no_news_electoral_baseline.md)

## Reproducing the release

Run these commands from the repository root (`irp-sl1425`). They rebuild from
committed local audits and do not download election pages:

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

.venv/bin/python -m pytest surrey-election-extractor/tests -q
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
university OneDrive. The extraction code, configuration, tests and compact
audit documentation remain version controlled for reproducibility.

[2017 Full Extraction (OneDrive)](https://imperiallondon-my.sharepoint.com/:f:/r/personal/sl1425_ic_ac_uk/Documents/IRP%20Surrey%20Election%20Extractor/2017%20Full%20Extraction?csf=1&web=1&e=DFwaAb)

## Source and inference policy

Official result fields are never filled from a lower evidence layer. A derived
or analysis value is published only when its inputs, formula, scope and source
are retained. Fuzzy candidate matching, UKIP/Reform merging, unapproved
boundary transfer and vote redistribution are prohibited.

The election master is release-ready with visible evidence boundaries. The
no-news input release now includes both the 339-row division history table and
a separate 1,603-row party-contest publication. Predictors and target-election
outcomes are stored separately; 775 single-member party contests have an
approved lagged party share for the primary baseline experiment. Model fitting,
temporal evaluation and release of baseline predictions remain downstream.
