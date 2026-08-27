# Surrey Election Results Extractor

This subproject builds the source-preserving Surrey County Council election
database used by the IRP (pipeline Layer 1A). It supplies the historical
election data for the no-news Stage 1 baseline against which the project tests
whether pre-election news adds predictive information beyond previous results.
The pipeline preserves source evidence, validates extracted values and produces
audit-ready feature and target datasets for downstream modelling; model fitting
and evaluation are downstream and are not part of this subproject. Not every
file is part of the production path: the complete file guide below groups every
module by function, and the main line is listed first.

Current release summary:

- 24 election events: the 2013, 2017 and 2021 principal elections, separate East
  and West Surrey 2026 elections, and 19 by-elections.
- 1,992 candidate rows and 343 division or ward rows.
- 24 reviewed 2021→2026 geographic relations and 205 approved historical
  references.
- Official values are never altered; supplementary, derived and analysis layers
  keep separate provenance and status fields, with publication gaps left visible.

## 1. The main line

`run_extraction_workflow` processes one principal-election, area-index or single
result URL in ordered stages: validate the URL, run a no-quota preflight,
discover every area so the published denominator is fixed (each configured
2013–2021 election requires all 81 divisions), extract the candidate table and
voting summary for each area, validate the records and build the workbook. For
every official page the retrieval order is: (1) the live official council page,
(2) the archived official copy from the Internet Archive, (3) indexed-search
evidence. Search snippets never overwrite official rows and missing source
values are never inferred.

The released datasets are rebuilt offline from committed audits, without
downloading election pages and without an API key. First create the
environment once (`python3 -m venv .venv && source .venv/bin/activate &&
pip install -r surrey-election-extractor/requirements.txt`), then run, in
this order, from the repository root (`irp-sl1425`):

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
  surrey-election-extractor/scripts/generate_no_news_candidate_contests.py
```

The last command writes `outputs/no_news_candidate_contests/` — the input
contract the Stage 1 baseline (`surrey-election-no-news-baseline/`) reads.

End-to-end hand-off:

```text
official pages / archives / indexed search
    -> run_extraction_workflow (validated workbooks)
    -> committed config/ evidence + audits
    -> generate_master_election_database.py (analytical payload)
    -> generate_no_news_candidate_contests.py
    -> surrey-election-extractor/outputs/no_news_candidate_contests/
    -> surrey-election-no-news-baseline/ (Stage 1 reads this release)
```

## 2. Complete file guide, grouped by function

One naming convention runs through the subproject:
`election_extractor/X.py` holds the pure logic, `scripts/generate_X.py` (or
`run_X.py`) is its runner writing one output or audit, and `tests/test_X.py`
tests it. The tables below list the logic modules; each has its paired runner
and test unless noted.

### 2.1 Extraction engine (the main line)

| File | Role |
|---|---|
| `workflow.py` | application-level orchestration for one extraction request |
| `discovery.py` | official-archive-first discovery of election areas |
| `extraction.py` | candidate-level result extraction from indexed evidence |
| `validation.py` | read-only validation of extracted result records |
| `completeness.py` | election, division and candidate completeness assessment |
| `workbook.py` | Excel workbook generation for validated results |
| `election_config.py` | declarative election configurations, loaded and validated |
| `official_source.py` | public-HTTP diagnostics for official result pages |
| `official_archive_fallback.py` | lawful archived-copy fallback when the official page is blocked |
| `url_utils.py` | validation and normalisation for official URLs |
| `models.py` | provider-neutral record models shared across stages |
| `search_providers/` | `base.py` interface, `serpapi.py` production adapter, `mock_provider.py` for API-key-free tests |
| `app.py` | thin Streamlit shell; collects inputs and calls `run_extraction_workflow`, all rules live in the library |
| `scripts/run_configured_election_pipeline.py` | runs the pipeline for one configured election |
| `scripts/run_2026_east_west_extraction.py` | runs the validated pipeline separately for East and West Surrey 2026 |

### 2.2 Compatibility audits (pre-run structure checks)

| File | Role |
|---|---|
| `compatibility_audit.py` | read-only evidence helpers for compatibility audits |
| `election_compatibility.py` | compatibility checks for configured elections |
| `election_2026_compatibility.py` | checks for the published 2026 Surrey map indexes |
| `scripts/run_2013_compatibility_audit.py`, `run_2026_compatibility_audit.py` | bounded, read-only audit runners; the committed 2026 audit output records that the East/West pages passed structure and multi-seat checks before extraction |

### 2.3 Master database and release audits

| File | Role |
|---|---|
| `master_database.py` | assembles the source-preserving multi-election analytical payload |
| `election_history.py` | evidence-gated election-event timeline and enrichment layer |
| `election_structure_metadata.py` | separately audited election-structure metadata |
| `supplementary_metadata.py` + `supplementary_metadata_audit.py` | additive supplementary evidence layer and its policies |
| `derived_metadata.py` | calculated values kept apart from official evidence |
| `division_supplementary_audit.py` | 2013 division evidence audit (no repairs to official data) |
| `final_data_release_audit.py` | release-readiness audit for the master database |
| `scripts/generate_layered_completeness_report.py`, `generate_2021_data_quality_report.py`, `generate_election_event_timeline.py`, `generate_2013_*` | per-election completeness, quality and timeline reports (committed under `outputs/`) |

### 2.4 Party and candidate identity

| File | Role |
|---|---|
| `party_lookup.py` | explicit, source-preserving party-name lookup; Reform UK and UKIP are never merged |
| `candidate_name_standardisation.py` | display-standard names without asserting identity |
| `candidate_continuity_evidence.py` | explicit evidence for candidate history and incumbency |
| `candidate_continuity_review.py` | review queue for repeated published names; no fuzzy matching |

### 2.5 Derived analysis fields (outcome side, never predictors)

| File | Role |
|---|---|
| `analysis_vote_share.py` | provenance-labelled candidate vote share for analysis |
| `analysis_voting_summary.py` | analysis-ready voting-summary values; official fields untouched |
| `derived_final_position.py` + `final_position_qa.py` | transparent vote ranks and their QA release |
| `derived_winning_margin.py` | single-seat winning margins from official rows |
| `change_in_vote_share.py` | outcome-only change in exact-label party share; excluded from no-news predictors by policy |

### 2.6 Geographic crosswalk (feeds the division sample and historical references)

| File | Role |
|---|---|
| `geographic_overlap_audit.py` | reviewable GIS overlap candidates from official public layers |
| `geographic_mapping_review.py` + `geographic_mapping_decision.py` + `geographic_mapping_audit.py` | review dataset, analytical comparability decisions, and the evidence audit for historical-to-2026 mapping |
| `geographic_crosswalk_resolution.py` | resolves GIS relationships into direct, partial and blocked outputs; its committed `final_direct_mapping_dataset.json` is the geographic evidence the local-news division sample cites |
| `population_weighted_crosswalk.py` | population-weighted 2021→2026 crosswalk estimates (audit only; votes are never redistributed) |

### 2.7 Historical references and the pre-news baseline

| File | Role |
|---|---|
| `historical_reference_permissions.py` | explicit permission audit for using historic areas as 2026 references (the 205 approved references) |
| `principal_election_continuity.py` | separate legal-continuity audit for pre-2024 principal elections |
| `historical_baseline.py` | evidence-gated historical baseline layer, built before any news modelling |

### 2.8 By-elections

| File | Role |
|---|---|
| `by_election_results.py` | evidence-backed by-election candidate results |
| `by_election_historical_reference.py` | eligibility audit for prior exact-label party-share baselines |
| `by_election_source_recovery.py` | read-only official-source recovery audit for the by-elections whose pages required news-archive verification |
| `scripts/generate_by_election_integration_audit.py` | integration and validation audit over the assembled by-election records |

### 2.9 No-news releases — the bridge to Stage 1

| File | Role |
|---|---|
| `no_news_baseline.py` | provenance-labelled electoral baseline, built before any news features exist |
| `no_news_candidate_contest.py` | candidate-contest modelling release; `surrey-election-no-news-baseline/` reads `outputs/no_news_candidate_contests/` as its input contract |

### 2.10 Evidence and policy inputs (`config/`)

Frozen, verified input evidence and policy as JSON; every record keeps its
source URL and validation status. These files hold manual judgement and are
not regenerable from code.

| File | Contents |
|---|---|
| `elections.json` | declarative election configurations, including the 81-division definitions each principal election must discover |
| `party_standardisation.json` | the explicit party-name lookup; Reform UK and UKIP stay separate |
| `historical_reference_permissions.json` | the approved historical area references with their statutory and GIS sources |
| `principal_election_continuity_permissions.json` | pre-2024 principal-election legal-continuity permissions |
| `geographic_crosswalk_resolution_policy.json`, `geographic_mapping_decision_policy.json` | the policies that resolve GIS relationships and decide analytical comparability |
| `geographic_overlap_audit.json`, `geographic_mapping_audit.json` | the reviewed GIS overlap candidates and mapping evidence records |
| `candidate_continuity_evidence.json` | explicit candidate history and incumbency evidence |
| `2013_division_turnout_evidence.json` | manual turnout evidence filling 2013 publication gaps |
| `supplementary_metadata.json`, `derived_metadata.json` | the additive supplementary evidence layer and the calculated values kept apart from official fields |
| `final_missing_field_evidence_index.json`, `final_position_second_source_reviews.json` | evidence index for fields official pages never published, and second-source reviews for derived positions |
| `by_election_event_catalogue.json`, `by_election_official_results.json`, `by_election_historical_reference_permissions.json`, `by_election_source_recovery_audit.json` | the 19 by-election events, their evidence-backed results, reference permissions and source-recovery decisions |

### 2.11 Committed audit outputs (`outputs/`)

Each directory is one committed, human-readable audit written by its
generator script; nothing in the pipeline reads them back.

| Directory | Produced by | What it proves |
|---|---|---|
| `2013/2017/2021_layered_completeness/`, `2026_east/west_layered_completeness/` | `generate_layered_completeness_report.py` | per-election completeness of the extraction against the fixed area denominator |
| `2021_data_quality_report/` | `generate_2021_data_quality_report.py` | the data-quality verdict over the completed 2021 audits |
| `2013_supplementary_metadata_audit/` | `generate_2013_supplementary_metadata_audit.py` | the bounded 2013 supplementary-metadata policy audit |
| `2026_compatibility_audit/` | `run_2026_compatibility_audit.py` | the East/West 2026 pages passed structure and multi-seat checks before extraction (chronology evidence) |
| `by_election_source_recovery/` | `generate_by_election_source_recovery_audit.py` | the official-source recovery trail for by-elections with missing pages |
| `election_event_timeline/` | `generate_election_event_timeline.py` | the evidence-gated event timeline and its data dictionary |
| `final_position_provenance_audit/` | `audit_final_position_provenance.py` | official pages publish no rank, so final position is a labelled derived field |
| `geographic_mapping_audit/`, `geographic_mapping_decision/`, `geographic_mapping_review/`, `geographic_crosswalk_resolution/`, `population_weighted_crosswalk/` | the matching `generate_geographic_*` / `generate_population_*` scripts | the reviewed 2021→2026 geography chain; `geographic_crosswalk_resolution/final_direct_mapping_dataset.json` is the committed evidence the local-news division sample cites |
| `historical_baseline_features/` | `generate_historical_baseline_features.py` | the historical-baseline feature dictionary and methodology |

### 2.12 Provenance audits and policies (`docs/`)

| File | Role |
|---|---|
| `election_data_readiness_audit.md` | the canonical current-state release summary (field coverage, counts, boundaries) |
| `historical_longitudinal_field_provenance_audit.md` | per-field provenance and evidence boundaries for every lagged/derived field |
| `supervisor_field_coverage_matrix.md` | supervisor-requested field coverage snapshot, tied to the release by `test_release_documentation.py` |
| `2013_byfleets/epsom_ewell_issued_ballots_audit.md`, `2013_elmbridge_issued_ballots_recovery_audit.md`, `2013_runnymede_archived_declarations_audit.md`, `2017_reigate_rejected_ballots_audit.md` | manual source-recovery audits for specific missing ballot values — unique human evidence behind committed config entries |
| `by_election_supplementary_metadata_audit.md`, `supplementary_metadata_governance.md` | the supplementary-metadata evidence audit and the governance hub linking the ballot audits |
| `candidate_and_incumbency_evidence_audit.md` | the official-evidence audit behind candidate history and incumbency fields |
| `change_in_vote_share_policy.md`, `winning_margin_derivation_policy.md` | derivation policies for the outcome-side analysis fields, including their exclusion from no-news predictors |
| `historical_reference_permission_audit.md`, `principal_election_continuity_audit.md` | the audits granting the historical references and pre-2024 continuity permissions |
| `historical_baseline_feature_layer.md`, `no_news_electoral_baseline.md`, `final_election_data_release_protocol.md` | the historical-baseline component note, the no-news baseline release note, and the final release protocol |
| `streamlit_extractor_release_verification.md`, `technical_notes.md` | the clean-environment application verification record and the parser/pagination/provider technical notes |

## 3. Source recovery and audit strategy

The live council site is served behind Imperva Incapsula bot protection and
often returns a challenge stub instead of the published tables. When that
happens the application does **not** attempt to bypass the protection: it falls
back to the lawful archived official copies held by the Internet Archive's
Wayback Machine, and only if the council page is blocked *and* no usable
archived copy exists does it switch to indexed-only mode. Every archived value
records its capture timestamp, the exact `web.archive.org` snapshot URL and the
extraction evidence, so archived values stay auditable and distinguishable from
live retrievals. Per-area audits retain attempt times, queries, result counts,
selected URLs and validation warnings; they never retain raw provider responses
or credentials.

## 4. The Streamlit application

The single-page application accepts a principal-election landing page, an
area-index URL or one official ward/division result URL, and produces a
workbook with an Index, one worksheet per area and an Extraction Log:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r surrey-election-extractor/requirements.txt
cd surrey-election-extractor && streamlit run app.py
```

The SerpAPI key is entered in a masked field, kept in memory for the request
only, and never written to project files or workbooks; no real key is included
in this repository. Area statuses: `Complete` (all required values present and
validated), `Incomplete` (published values missing or under review; blanks are
listed in the audit, never filled), `Failed` (no reliable data extractable).
The clean-environment release checks are recorded in
[`docs/streamlit_extractor_release_verification.md`](docs/streamlit_extractor_release_verification.md).

## 5. Outputs and reproducibility

The primary generated files are the master database payload, schema and audit
summary, the final release audit, and the no-news baseline and contest
releases (paths under `outputs/`). Generated workbooks and large research
outputs are stored outside Git on the university OneDrive; the code,
configuration, tests and compact audit documentation remain version
controlled, and the release rebuilds offline from the committed audits, so the
workbooks are not required to reproduce it. One representative full extraction
is linked as an example:

[Representative 2017 full extraction, sample only (OneDrive)](https://imperiallondon-my.sharepoint.com/:f:/r/personal/sl1425_ic_ac_uk/Documents/IRP%20Surrey%20Election%20Extractor/2017%20Full%20Extraction?csf=1&web=1&e=DFwaAb)

## 6. Verifying this directory without an API key

The test suite runs offline against mocked official pages and indexed results
— no live SerpAPI key is required or consumed. From `surrey-election-extractor/`
with the project environment activated:

```bash
python -m pytest -q
```

397 tests cover every logic module, the runners and the application acceptance
path; the acceptance tests reopen generated workbook bytes with `openpyxl` and
verify the expected sheets, values, blank cells, hyperlinks and audit
structure.

## 7. Limitations and the source-and-inference policy

Official result fields are never filled from a lower evidence layer; a derived
or analysis value is published only when its inputs, formula, scope and source
are retained. Fuzzy candidate matching, UKIP/Reform merging, unapproved
boundary transfer and vote redistribution are prohibited. An official page can
omit a value (the export keeps the field blank and marks the area Incomplete
rather than writing a calculated zero); indexed titles and snippets can be
incomplete or truncated; evidence is combined only when election, area and
result URL match; and archived copies reproduce the official page as captured,
gaps included. Predictors and target-election outcomes are stored separately:
the no-news input release includes the 343-row division history table and the
1,992-row candidate-contest release that the Stage 1 baseline consumes as its
input contract.
