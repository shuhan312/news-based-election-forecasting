# Surrey Election Extractor — Experiment Process Log

**Local working record**  
**Created:** 16 July 2026  
**Repository:** `irp-sl1425/surrey-election-extractor`  
**Purpose:** Record completed experimental and data-engineering steps in this working session. This document describes process, evidence handling, generated artefacts and known boundaries. It does not make predictive, causal or substantive electoral conclusions.

## 1. Research workflow boundary

The project is designed to assess, at a later stage, whether pre-election news context adds predictive information beyond historical election information. The completed work in this record is limited to election-data collection, source provenance, validation, geographic comparability and historical-baseline preparation.

No NewsAPI collection, news scraping, article classification, LLM classification, prediction modelling or vote redistribution was started in the recorded workflow.

## 2. Repository and reproducibility setup

The repository was structured as a Python project with separate components for:

- discovery of official Surrey election result URLs;
- official-source parsing and candidate-level extraction;
- validation and layered completeness assessment;
- workbook generation;
- supplementary metadata;
- election configuration and compatibility assessment;
- geographic mapping and crosswalk resolution;
- event timeline and historical baseline preparation.

Automated tests use mocked fixtures where live retrieval is not required. API keys and private credentials are excluded from source control through `.gitignore`.

## 3. Official election discovery and extraction

### 3.1 Discovery

The discovery layer was developed to identify official Surrey County Council election result URLs using indexed search evidence and recognised Surrey result URL patterns. It normalises URLs, preserves meaningful query parameters, rejects invalid URLs, removes duplicates and records search attempts.

Discovery metadata completeness was later separated from result-link validity. A verified official result URL can therefore remain discovered even where page-local election metadata is absent. This was necessary for the 2017 official result pages, which were valid result pages but did not publish all election-level metadata locally.

### 3.2 Candidate-level extraction

The extraction layer was implemented to create one record per published candidate. It preserves the original published candidate name, party wording, votes, vote share, published outcome, result URL and missing-field information.

The extraction process does not create candidates, parties, results or numeric values that are absent from a source page. Original party wording is retained separately from any reviewed standardised label. UK Independence Party / UKIP and Reform UK remain distinct.

### 3.3 Principal election inputs processed

The following completed official extraction audit inputs were used by later database, timeline and baseline stages:

| Election input | Official divisions / wards | Candidate records |
| --- | ---: | ---: |
| Surrey County Council Election 2013 | 81 | 358 |
| Surrey County Council Election 2017 | 81 | 377 |
| Surrey County Council Election 2021 | 81 | 331 |
| Surrey County Council Election 2026 — East Surrey | 36 | 379 |
| Surrey County Council Election 2026 — West Surrey | 45 | 453 |

The two 2026 source regions remain separate inputs. They were not combined with historical divisions without reviewed geographic evidence.

## 4. Official Voting Summary and Seats handling

Official result pages were investigated for Voting Summary fields: Seats, total votes, electorate, ballot papers issued, rejected ballots and turnout.

The data flow from official-page parsing through extraction, models and validation was checked. The rule applied throughout is:

> An official page's published `Seats` value is the only source for `official_number_of_seats`.

No seat count was inferred from election year, number of winners or number of candidates. Where an official Seats field was not published, it remained missing in official extraction data.

For 2021, a separate supplementary election-structure metadata layer was added after review of statutory evidence. The layer stores secondary Seats evidence separately from official result-page values. It does not overwrite missing official fields and does not automatically change an incomplete official record into a complete one.

## 5. Completeness and provenance assessment

Completeness was separated into three levels:

1. **Election level:** election name, date, type and authority; configuration can provide election-level information where individual result pages do not.
2. **Division / ward level:** division name, seats, electorate, ballot papers, rejected ballots and turnout; official missing values remain missing for that area only.
3. **Candidate level:** candidate name, original party, votes, vote share and elected status; candidate completeness does not require election-level metadata or division summary fields.

This avoids treating every candidate record as incomplete merely because a page does not repeat election-level text. It does not fill missing official values.

An additional final-position provenance audit examined representative official candidate tables for 2017 and 2021. No official position, rank, placing or equivalent field was used to calculate `final_position`; the field remains `NULL` where it is not published.

## 6. Election configuration and compatibility checks

An election configuration layer was created for 2013, 2017, 2021, 2026 East Surrey and 2026 West Surrey. It validates required fields, URLs and unique election identifiers without hard-coding election-year rules into extraction logic.

Compatibility checks were carried out before new principal-election extraction. They inspect archive access, result-link patterns, representative page structures and the availability of Voting Summary fields. These checks are diagnostic only and do not fill data.

## 7. Workbook and unified analytical database

Workbook generation was implemented using `openpyxl`, retaining source data, validation information, missing fields and extraction status. The workbook logic keeps published extracted values separate from calculated validation values.

A unified analytical database was then constructed from the completed principal-election audit inputs. It contains source-preserving tables for elections, candidate results, divisions and wards, candidates, parties, party history, supplementary metadata and data dictionary information. The separate 2026 East and West inputs remain distinct.

Generated workbook files and detailed audit JSON files are treated as reproducible outputs rather than normal Git source files. Large or intermediate outputs are kept locally or should be stored in the approved OneDrive location rather than committed to GitHub.

## 8. 2013 supplementary metadata review

A supplementary metadata audit examined source options for 2013 fields not consistently published on official individual result pages.

The review retained a distinction between:

- official result-page data;
- separately documented supplementary evidence; and
- unavailable values.

Supplementary values were not written into official fields. The audit recorded source URL, field, geographic level, evidence text and reliability assessment. Wikipedia was treated only as a possible secondary source and was not used to replace official candidate-level data.

## 9. Geographic Mapping Decision and Crosswalk Resolution

Historical Surrey divisions and 2026 wards have different boundaries. A geographic evidence framework was implemented before any cross-election comparison features were allowed.

The reviewed Crosswalk Resolution Layer classifies relationships as:

| Geographic status | Reviewed relationship rows |
| --- | ---: |
| `accepted_direct` | 22 |
| `partial_crosswalk_available` | 75 |
| `not_comparable` | 43 |
| `requires_review` | 27 |

The key analytical restriction is:

> Only an `accepted_direct` relationship may support a direct historical electoral comparison.

Partial crosswalks describe boundary topology only. They are not used for vote redistribution, vote-share change, swing, candidate transfer, incumbency, predecessor assignment or previous-winner assignment. `not_comparable` and `requires_review` relationships remain blocked for those uses.

## 10. Election event timeline and safe enrichment

An evidence-gated event timeline was created from the five principal election inputs and the official archive’s indexed by-election listing.

### 10.1 Event coverage

- Principal election events represented: 5.
- By-election events catalogued separately: 15.
- Total event identifiers represented: 20.
- Principal candidate records preserved in the timeline dataset: 1,898.

Each event record contains election identifier, type, date, authority, area identifier and name, source URL, provenance and geographic identity status. Candidate rows retain original party labels, votes, vote share, outcome and source information.

### 10.2 By-election status

The 15 by-election events currently have official archive-listing evidence for event name, date and area. Their candidate-level result data has not been added because corresponding official event-result page evidence was not retrieved in this workflow.

Therefore, by-election candidate rows, votes, vote share, elected status, turnout and Seats remain `NULL` / unavailable. No zero-row results, candidates or outcomes were invented.

### 10.3 Safe enrichment performed

The timeline creates factual, non-comparative enrichments only:

- published candidate-row count;
- published party count;
- source-reported Seats where present;
- turnout, electorate and rejected-ballot availability indicators;
- exact-label party appearance history; and
- chronology links only where a valid direct identity exists.

Candidate names are not treated as personal identifiers. Candidate appearance history, incumbency and predecessor transfer remain unavailable without explicit identity evidence.

## 11. Historical Baseline Feature Layer

The Historical Baseline Feature Layer was created to prepare the election-history-only information that could later serve as a no-news comparator. It is not a prediction model.

### 11.1 Baseline outputs

The local generated output set contains:

- documented historical baseline feature schema;
- 2026 ward baseline feature table;
- exact-label party-history feature table;
- candidate-history infrastructure table;
- 2026 baseline readiness dataset;
- feature dictionary; and
- methodology document.

### 11.2 Features available without geographic comparison

For all 81 2026 wards, the layer records source or deterministic structure information where available:

- election date and type;
- number of published candidates;
- number of distinct original party labels;
- official Seats value where published;
- candidate and party competition categories;
- availability of turnout, electorate and rejected-ballot values.

### 11.3 Direct historical references

For the 22 2026 wards with exactly one `accepted_direct` relationship, the layer may reference the latest earlier principal event for the explicitly mapped historical area. Where source fields are available, the reference includes:

- source election event and official result URL;
- source-reported elected candidate and original winning party;
- published elected candidate vote share;
- source turnout and electorate;
- candidate and party counts from the earlier event; and
- geographic mapping identifier and evidence summary.

These values remain separately traceable to their source election and geographic evidence. No vote change, swing or redistribution is calculated.

### 11.4 Blocked baseline features

For 2026 ward-level readiness classification, the current distribution is:

| Ward readiness status | Wards |
| --- | ---: |
| `accepted_direct` baseline available | 22 |
| `partial_crosswalk_available` baseline blocked | 36 |
| `requires_review` baseline blocked | 23 |

`not_comparable` relationships remain present in supporting geographic evidence. They do not enable a direct baseline. Some wards have more than one retained GIS relationship; a separate low-overlap relationship does not replace an approved direct relationship, and a partial/review relationship never becomes direct.

The following are intentionally blocked for all wards unless separately evidenced in a future approved task:

- vote redistribution;
- party vote-share change;
- party swing;
- candidate identity transfer;
- incumbency transfer; and
- predecessor councillor transfer.

Candidate-history infrastructure was created for 832 current 2026 candidate records, but every candidate remains `unresolved_no_explicit_identifier`. Identical names are not used to infer identity.

Party-history features use exact original published party labels in accepted direct historical lineages. UK Independence Party and Reform UK remain separate.

## 12. Verification performed

The project test suite was run after the Historical Baseline Feature Layer was added:

- automated tests: **180 passed**;
- Python compilation check: completed successfully;
- Git whitespace check: completed successfully.

Tests include safeguards for unavailable values, partial and not-comparable geographic status, candidate name-only matching, UK Independence Party / Reform UK separation, raw extraction immutability and direct-mapping-only historical reference generation.

## 13. Current boundaries for a future session

The following work has not been started in this process record:

- candidate-level extraction for the catalogued by-elections;
- NewsAPI searches or local news archive searches;
- article extraction or classification;
- LLM context extraction;
- predictive model training or validation;
- vote-share change or swing calculation;
- electoral comparison using partial, not-comparable or requires-review geographic relationships.

Any later by-election result integration should first obtain and validate the relevant official result-page evidence, then use the existing discovery, extraction and validation workflow. Any future news-model work should compare against the documented historical baseline rather than treating historical features as an afterthought.

## 14. Local output locations

Relevant reproducible local outputs are under:

- `surrey-election-extractor/outputs/election_event_timeline/`
- `surrey-election-extractor/outputs/historical_baseline_features/`
- `surrey-election-extractor/outputs/geographic_crosswalk_resolution/`

Large JSON audits, workbooks and other intermediate generated files should remain outside normal Git commits. The repository retains the code, configuration, tests and small documentation needed to regenerate them.
