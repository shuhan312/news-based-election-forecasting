# Surrey Election Supplementary Metadata Governance

## Purpose and layer boundary

The project keeps three information layers separate:

1. **Official data** contains only values published by an official election-result source.
2. **Configuration metadata** identifies the election (for example, election name, date, type and authority).
3. **Supplementary metadata** records reviewed external evidence with its own source URL, evidence text, retrieval date and confidence.

Supplementary metadata is an additive evidence table. It never overwrites an official field, fills a missing official value, changes layered completeness, or supplies candidate votes.

## Reusable record design

Every record has `metadata_id`, `election_id`, optional `division_id`, optional `candidate_name`, `field_name`, `value`, `geographic_level`, `source_type`, `source_name`, `source_url`, `evidence_text`, `retrieval_date`, `confidence`, optional `notes` and `validation_status`.

Permitted geographic levels are `election`, `division` and `candidate`. Division and candidate evidence require the matching official `division_id`; candidate evidence also requires the exact published candidate name. A source URL and supporting evidence text are mandatory for every value.

## Audit of completed elections

| Election | Field | Official availability | Supplementary evidence status | Storage decision |
| --- | --- | --- | --- | --- |
| 2013 | turnout | Division turnout is absent from the official result-page summaries. | The Surrey Council announcement provides 80 named division turnout values; its county-wide 30% figure is also independently supported by the Electoral Commission. | 80 verified `secondary_division_turnout` records and two `secondary_election_turnout` records; none overwrite official division fields. |
| 2013 | ballot_papers_issued | Absent from official division summaries. | Potential named Woking evidence was reviewed but has not been integrated division by division. | Remains NULL in official fields; no generic record yet. |
| 2017 | rejected_ballots | Reigate's official page does not publish the value. | No approved supplementary evidence. | Remains NULL. |
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
- Never replace or calculate an official value.

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

The approved 2013 evidence registers contain 80 verified division-level records for `secondary_division_turnout`, each tied to a named Surrey Council result section. Foxhills, Thorpe & Virginia Water remains unresolved because the named section displays a turnout label without a value. No `ballot_papers_issued` value is currently accepted.

They also contain two verified, election-level records for `secondary_election_turnout = 30.0`:

- Surrey County Council, *Election results declared*.
- Electoral Commission, *Results and turnout at the May 2017 England local elections*.

The master workbook's **Supplementary Metadata** tab shows all approved evidence independently. The official `turnout` cells for all 81 2013 divisions remain blank, and their division completeness remains unchanged.

The [by-election supplementary metadata audit](by_election_supplementary_metadata_audit.md) records the reviewed source scope for the remaining by-election gaps, including the separate Addlestone 2025 turnout evidence and one corrected official Staines candidate row.
