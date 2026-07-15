# Election Compatibility Report: County Council Election 2021

## Election

- Election ID: surrey-county-council-2021
- Year: 2021
- Type: County Council election
- Archive URL: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0

## Compatibility

- Overall status: compatible
- Recommendation: A later, separately approved extraction run can use the existing pipeline.

## Archive and discovery

- Archive status: accessible
- Archive evidence: HTTP status=200; expected election information present=yes; error=none.
- Result pages found: 1
- Duplicate URLs removed: 1
- URL patterns: /mgElectionAreaResults.aspx

## Result page structure

- Candidate fields available: {'candidate name': True, 'party name': True, 'votes': True, 'vote share': True, 'elected status': True}
- Summary fields available: {'seats': True, 'total votes': True, 'electorate': True, 'ballot papers issued': True, 'rejected ballots': True, 'turnout': True}
- HTML/table patterns: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=258&RPID=0: candidate_rows=1; voting_summary_label=yes

## Seats metadata

- Seats source: official_result_page
- Supplementary metadata required: False
- Evidence: Seats was observed in a representative official Voting Summary.

## Risks

- None observed.

## Provenance

- Archive source: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0
- Representative result pages: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=258&RPID=0
- Inspection mode: mocked_read_only_representative_html
