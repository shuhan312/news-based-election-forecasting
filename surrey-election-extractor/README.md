# Surrey Election Results Extractor

This project builds a source-preserving Surrey County Council election database
for testing whether pre-election news improves winning-party and party-vote-
share predictions beyond previous election results.

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

.venv/bin/python -m pytest surrey-election-extractor/tests -q
```

The primary generated files are:

- `outputs/master_surrey_election_database/master_election_database_payload.json`
- `outputs/master_surrey_election_database/master_election_database_schema.md`
- `outputs/master_surrey_election_database/master_election_database_audit_summary.md`
- `outputs/final_election_data_release_audit/final_election_data_release_audit.json`
- `outputs/no_news_electoral_baseline/no_news_electoral_baseline.json`

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
current no-news division-level export is leakage-safe, but a separate
candidate/party-level lagged-share export remains necessary before the complete
party-vote-share baseline can be called model-ready.
