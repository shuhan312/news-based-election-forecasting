# Election Compatibility Report: Surrey County Council Election 2017

## Election

- Election ID: surrey-county-council-2017
- Year: 2017
- Type: County Council election
- Archive URL: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0

## Compatibility

- Overall status: compatible
- Recommendation: A later, separately approved extraction run can use the existing pipeline.

## Archive and discovery

- Archive status: accessible
- Archive evidence: HTTP status=200; expected election information present=yes; error=none.
- Result pages found: 81
- Unique divisions found: 81
- Accepted divisions: 81
- Duplicate URLs removed: 162
- URL patterns: /mgElectionAreaResults.aspx

## Result page structure

- Candidate fields available: {'candidate name': True, 'party name': True, 'votes': True, 'vote share': True, 'elected status': True}
- Summary fields available: {'seats': True, 'total votes': True, 'electorate': True, 'ballot papers issued': True, 'rejected ballots': True, 'turnout': True}
- HTML/table patterns: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=173&RPID=453819663&XXR=0: candidate_rows=5; voting_summary_label=yes | https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=174&RPID=453819663&XXR=0: candidate_rows=5; voting_summary_label=yes | https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=175&RPID=453819663&XXR=0: candidate_rows=6; voting_summary_label=yes
- Structural differences from 2021: No candidate or non-Seats Voting Summary field difference was observed in the representative pages.

## Seats metadata

- Seats source: official_result_page
- Supplementary metadata required: False
- Evidence: Seats was observed in a representative official Voting Summary.

## Risks

- None observed.

## Provenance

- Archive source: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0
- Representative result pages: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=173&RPID=453819663&XXR=0, https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=174&RPID=453819663&XXR=0, https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=175&RPID=453819663&XXR=0
- Inspection mode: read_only_existing_discovery_and_representative_html
