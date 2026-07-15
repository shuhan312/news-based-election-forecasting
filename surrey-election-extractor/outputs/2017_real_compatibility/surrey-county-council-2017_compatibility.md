# Election Compatibility Report: Surrey County Council Election 2017

## Election

- Election ID: surrey-county-council-2017
- Year: 2017
- Type: County Council election
- Archive URL: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0

## Compatibility

- Overall status: requires_changes
- Recommendation: Do not extract yet. Review the listed archive, discovery or page-structure risks before changing the pipeline.

## Archive and discovery

- Archive status: accessible
- Archive evidence: HTTP status=200; expected election information present=yes; error=none.
- Result pages found: 81
- Unique divisions found: 81
- Accepted divisions: 0
- Duplicate URLs removed: 162
- URL patterns: /mgElectionAreaResults.aspx

## Result page structure

- Candidate fields available: {'candidate name': True, 'party name': True, 'votes': True, 'vote share': True, 'elected status': True}
- Summary fields available: {'seats': True, 'total votes': True, 'electorate': True, 'ballot papers issued': True, 'rejected ballots': True, 'turnout': True}
- HTML/table patterns: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=173&RPID=453812759&XXR=0: candidate_rows=5; voting_summary_label=yes | https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=174&RPID=453812759&XXR=0: candidate_rows=5; voting_summary_label=yes | https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=175&RPID=453812759&XXR=0: candidate_rows=6; voting_summary_label=yes
- Structural differences from 2021: No candidate or non-Seats Voting Summary field difference was observed in the representative pages. | Discovery-level difference from the 2021 baseline: official result URLs were observed but not accepted because the 2017 archive/index pages did not provide election metadata in the format required by existing discovery.

## Seats metadata

- Seats source: official_result_page
- Supplementary metadata required: False
- Evidence: Seats was observed in a representative official Voting Summary.

## Risks

- 81 official result URLs were not accepted by discovery: missing_election_metadata.
- Existing discovery did not accept any official division result URLs.

## Provenance

- Archive source: https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0
- Representative result pages: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=173&RPID=453812759&XXR=0, https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=174&RPID=453812759&XXR=0, https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=175&RPID=453812759&XXR=0
- Inspection mode: read_only_existing_discovery_and_representative_html
