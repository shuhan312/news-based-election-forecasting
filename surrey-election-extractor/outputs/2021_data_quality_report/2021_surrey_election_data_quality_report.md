# 2021 Surrey County Council Election Data Quality Report

## 1. Dataset overview

- Election: County Council Election 2021
- Year: 2021
- Authority: Surrey County Council
- Divisions: 81
- Official result pages: 81
- Candidate-level records: 331

## 2. Extraction coverage

- Successfully processed divisions: 81
- Failed divisions: 0
- Missing divisions relative to the official archive: 0
- Invented divisions: 0
- All 81 divisions enumerated by the official archive were processed. No division was invented or omitted relative to that archive list.

## 3. Candidate data quality

- Total candidates: 331
- Candidates per division: minimum 2, maximum 7, average 4.09
- Distribution: 2 candidates: 1 divisions, 3 candidates: 19 divisions, 4 candidates: 40 divisions, 5 candidates: 15 divisions, 6 candidates: 5 divisions, 7 candidates: 1 divisions
- Provenance: All 331 candidate records have source_type=official and retain their official Surrey result-page URL and field-level evidence.

| Candidate field | Available records | Missing records |
|---|---:|---:|
| candidate_name | 331 | 0 |
| original_party_name | 331 | 0 |
| votes_received | 331 | 0 |
| vote_share | 331 | 0 |
| outcome | 331 | 0 |

## 4. Election summary fields

| Field | Official divisions available | Official divisions missing | Candidate records available | Candidate records missing | Source |
|---|---:|---:|---:|---:|---|
| seats | 53 | 28 | 222 | 109 | Surrey County Council official result page Voting Summary |
| total_votes | 81 | 0 | 331 | 0 | Surrey County Council official result page Voting Summary |
| electorate | 81 | 0 | 331 | 0 | Surrey County Council official result page Voting Summary |
| ballot_papers_issued | 81 | 0 | 331 | 0 | Surrey County Council official result page Voting Summary |
| rejected_ballots | 81 | 0 | 331 | 0 | Surrey County Council official result page Voting Summary |
| turnout | 81 | 0 | 331 | 0 | Surrey County Council official result page Voting Summary |

## 5. Seats handling

- Official Seats: Official number_of_seats is populated only when Surrey's official result page publishes a Seats row in its Voting Summary.
- Missing official Seats: A missing official Seats row remains missing. It is not inferred from the election year, candidate count, elected candidates or historical assumptions.
- Secondary Seats: For the 28 affected divisions, separately stored supplementary metadata records a secondary Seats value of 1 with its source, evidence text and confidence.
- Source: The Surrey (Electoral Changes) Order 2012 (UKSI 2012/1872)
- Why separate: The official result page and the statutory source are different provenance layers. Keeping them separate preserves the published official value, its absence, and the uncertainty that absence represents.

## 6. Validation summary

- Division statuses: {'Incomplete': 28, 'Passed': 53}
- Candidate record statuses: {'Complete': 222, 'Incomplete': 109, 'Failed': 0}
- Validation checks performed: {'candidate_vote_total': 81, 'extraction_status': 81, 'missing_data': 81, 'turnout': 81, 'vote_share': 331}
- Validation-event outcomes: {'Incomplete': 56, 'Passed': 599}
- Warnings: 0; failed checks: 0
- The 109 incomplete candidate records belong to 28 divisions whose official page did not publish Seats. They are not evidence of an extraction failure.

## 7. Known limitations

- Twenty-eight official result pages do not publish a Seats field in their HTML.
- Official result pages vary in whether the Seats row is published, so source availability is not uniform.
- Secondary Seats metadata is supplementary only and must not replace official_number_of_seats.
- The report describes the verified 2021 archive run; it does not claim coverage of other election years.

## 8. Reproducibility

- Official archive: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0
- Official result URL audit: `/Users/sl1425/irp-sl1425/surrey-election-extractor/outputs/2021_archive_discovery_pilot/2021_archive_discovery_pilot_audit.json`
- Seats diagnosis: `/Users/sl1425/irp-sl1425/surrey-election-extractor/outputs/2021_seats_diagnosis_verified/2021_official_seats_diagnostic.json`
- Secondary Seats audit: `/Users/sl1425/irp-sl1425/surrey-election-extractor/outputs/2021_secondary_seats_audit/2021_secondary_seats_audit.json`
- Generated workbook: `/Users/sl1425/irp-sl1425/surrey-election-extractor/outputs/2021_archive_discovery_pilot/surrey_county_council_2021_archive_discovery_pilot.xlsx`
- Tests: 75 passed (full project test suite, 2026-07-15)

## Conclusion

The 2021 dataset has complete archive and official-page coverage. Its remaining official Seats gaps reflect fields not published by 28 official result pages, rather than extraction failure. The system preserves this uncertainty and retains separate source-backed metadata.
