# Surrey Election Supplementary Metadata Governance

## Purpose and layer boundary

The project keeps three information layers separate:

1. **Official data** contains only values published by an official election-result source.
2. **Configuration metadata** identifies the election (for example, election name, date, type and authority).
3. **Supplementary metadata** records reviewed external evidence with its own source URL, evidence text, retrieval date and confidence.

Supplementary metadata is an additive evidence table. It never overwrites an official field, fills a missing official value, changes layered completeness, or supplies candidate votes.

## Derived metadata layer

Derived metadata is a fourth, separate layer for a calculation based entirely
on values explicitly published on **one** official result page. It is neither
official extraction data nor supplementary-source evidence. A derived record
never overwrites an official field, changes extraction status, or changes
layered completeness.

The current project allows a derived value only when all of the following are
true:

1. The formula is explicitly allow-listed in code and recorded verbatim.
2. Every input value is explicitly published on the same audited official
   result URL, and the configured inputs exactly match the extracted values.
3. The target official field is genuinely missing; a calculation cannot
   duplicate or replace a published official value.
4. The formula reproduces the recorded value exactly and produces a
   non-negative result.
5. The record retains the official source URL, evidence text, retrieval date,
   confidence, input values, validation status and a non-overwrite note.

The approved formulas are `ballot_papers_issued - total_votes`, stored as
`derived_rejected_ballots`, and `total_votes + rejected_ballots`, stored as
`derived_ballot_papers_issued`. Both are permitted only after the checks above
and are displayed in the separate **Derived Metadata** table. A new formula
requires a code change, tests and review; it cannot be introduced by
configuration alone.

## Reusable record design

Every record has `metadata_id`, `election_id`, optional `division_id`, optional `candidate_name`, `field_name`, `value`, `geographic_level`, `source_type`, `source_name`, `source_url`, `evidence_text`, `retrieval_date`, `confidence`, optional `notes` and `validation_status`.

Permitted geographic levels are `election`, `division` and `candidate`. Division and candidate evidence require the matching official `division_id`; candidate evidence also requires the exact published candidate name. A source URL and supporting evidence text are mandatory for every value.

## Audit of completed elections

| Election | Field | Official availability | Supplementary evidence status | Storage decision |
| --- | --- | --- | --- | --- |
| 2013 | turnout | Division turnout is absent from the official result-page summaries. | The Surrey Council announcement provides 80 named division turnout values. Wikipedia supplies Foxhills, Thorpe & Virginia Water's 27% only after ten other named Wikipedia values were checked against the Council publication; its county-wide 30% figure is also independently supported by the Electoral Commission. | 81 verified `secondary_division_turnout` records and two `secondary_election_turnout` records; none overwrite official division fields. |
| 2013 | ballot_papers_issued | Absent from Surrey's official division summaries. | Woking Borough Council's signed declaration names seven Woking divisions; Epsom & Ewell Borough Council official result pages name five Epsom & Ewell divisions. All twelve sources have exact candidate-vote-list matches; The Byfleets retains an explicit three-voter electorate discrepancy and the Epsom & Ewell pages do not publish electorate. Surrey's own official pages publish `total_votes` and `rejected_ballots` for all 81 divisions. | Twelve verified `secondary_division_ballot_papers_issued` records, plus 81 separate `derived_ballot_papers_issued` records. Surrey official fields remain NULL. All source limitations are retained in the supplementary evidence. |
| 2017 | rejected_ballots | Reigate's Surrey result page and the archived Reigate & Banstead 2017 results page do not publish the value. | No source containing a published rejected-ballot count was recovered from the reviewed Surrey, borough and Internet Archive source set. | Remains NULL; the scoped audit is documented in [2017 Reigate rejected-ballot audit](2017_reigate_rejected_ballots_audit.md). |
| 2021 | Seats | 28 official result pages do not publish Seats. | The Surrey (Electoral Changes) Order 2012 names the affected divisions and provides one councillor for each. | Existing verified division-level supplementary Seats records remain separate from official Seats. |
| 2016 and 2025 by-elections | Staines South & Ashford West and Addlestone turnout | The Surrey result pages do not publish turnout. | Spelthorne Borough Council explicitly reports 31.3% for Staines South & Ashford West; Runnymede Borough Council explicitly reports 24% for the same Addlestone County Division by-election. | Two verified `secondary_division_turnout` records; official turnout fields remain NULL. |
| 2013, 2017, 2021 | final_position | Not published in the official candidate result tables. | No secondary evidence is approved for ranking. | Remains NULL; never calculated from votes. |
| 2013 Lingfield | D'Avray party affiliation | The official Lingfield result-page Party cell is blank. | A separate Surrey County Council election announcement says “No party affiliation”. | One candidate-level supplementary evidence record; the official Party field and standardised party fields remain NULL. |

## Field policies

### Turnout

- Store official turnout only in the official division `turnout` field.
- Store a named, explicitly stated division turnout only as a separate division-level metadata record.
- Store election-wide supplementary turnout only as a separate election-level metadata record.
- Never propagate election-wide turnout into division records or completeness.

### Ballot papers issued

- Store an official published value in the official division field.
- A future exact division-level external source may be recorded in supplementary metadata only after a named-division evidence audit.
- Never replace or calculate an official value. A distinct derived record may
  use `total_votes + rejected_ballots` only when the same official result page
  explicitly publishes `Seats = 1`, both exact inputs, and a missing official
  issued field. It is never applied from an election-year assumption, and all
  derived-layer validation rules above must pass.

### Final position

- Official result pages are the only permitted source.
- Keep `final_position` NULL when not published.
- Never calculate rank or placing from votes, candidate order or outcomes.

### Candidate-party affiliation

- Preserve the individual official result page's published Party cell exactly, including a blank cell.
- A separate official Council publication can be recorded only as `supplementary_candidate_party_affiliation`, with the exact candidate name and matching official division ID.
- Do not convert that evidence into `original_party_name`, `standard_party_name` or a party category. In particular, do not turn “No party affiliation” into `Independent` without an approved, source-specific policy.

### Seats

- Preserve official Seats in `official_number_of_seats`.
- Store verified secondary Seats as separate supplementary metadata.
- A secondary Seats value never replaces an officially missing Seats value and cannot change division completeness.

## Current approved integration

The approved 2013 evidence registers contain 81 verified division-level records for `secondary_division_turnout`. Eighty are tied directly to named Surrey Council result sections. The remaining Foxhills, Thorpe & Virginia Water value of 27% is a separate Wikipedia secondary record: its table reproduces the named division and turnout, and ten other named Wikipedia turnout values were checked against the Surrey Council publication before acceptance. No `ballot_papers_issued` value is currently accepted for Foxhills.

They also contain two verified, election-level records for `secondary_election_turnout = 30.0`:

- Surrey County Council, *Election results declared*.
- Electoral Commission, *Results and turnout at the May 2017 England local elections*.

The master workbook's **Supplementary Metadata** tab shows all approved evidence independently. The official `turnout` cells for all 81 2013 divisions remain blank, and their division completeness remains unchanged.

The Woking declaration supports seven named 2013 `secondary_division_ballot_papers_issued` values: Goldsworth East and Horsell Village, Knaphill and Goldsworth West, The Byfleets, Woking North, Woking South, Woking South East and Woking South West. Six source electorates match the Surrey result page. For The Byfleets, Woking states `10,016` while Surrey states `10,019`; its source record is accepted only because the official declaration also gives the same date, division, five candidates, candidate vote list and winner. A second Surrey Council announcement independently corroborates the rounded 29% turnout. The two electorates remain visible in the supplementary note and the official Surrey electorate is never replaced; see the [Byfleets issued-ballots audit](2013_byfleets_issued_ballots_audit.md).

Epsom & Ewell Borough Council's official result pages support five additional values: Epsom Town & Downs, Epsom West, Ewell, Ewell Court, Auriol & Cuddington, and West Ewell. Each page identifies the 2013 Surrey County Council election, its named division and complete candidate vote list. These pages do not publish electorate, so each supplementary record explicitly records that source limitation and is accepted only after its complete vote list matches Surrey's official page; see the [Epsom & Ewell issued-ballots audit](2013_epsom_ewell_issued_ballots_audit.md).

The [by-election supplementary metadata audit](by_election_supplementary_metadata_audit.md) records the reviewed source scope for the remaining by-election gaps, including the separate Addlestone 2025 turnout evidence, one corrected official Staines candidate row, and three strictly governed derived issued-ballot values.

## Current derived calculation

The [derived metadata register](../config/derived_metadata.json) contains one
verified record for Reigate 2017, one reviewed 2013 rule, three reviewed
one-seat by-election issued-ballot rules, and one one-seat by-election
total-vote rule. Reigate's official
result page publishes both `ballot_papers_issued = 4,109` and `total_votes =
4,109`, while its official `rejected_ballots` field remains absent. The derived
layer records `derived_rejected_ballots = 0`. The 2013 rule creates one
`derived_ballot_papers_issued` record only where the same official Surrey page
publishes `Seats = 1`, `total_votes` and `rejected_ballots`; all 81 pages
currently satisfy those source-input checks. The three by-election rules apply
the same one-seat safeguard to Staines South & Ashford West 2016, Haslemere
2019 and Addlestone 2025. Epsom West 2015 separately derives total votes as
issued ballot papers minus rejected papers from its signed declaration. Neither
calculation populates an official column, produces a candidate vote share or
changes division completeness.
