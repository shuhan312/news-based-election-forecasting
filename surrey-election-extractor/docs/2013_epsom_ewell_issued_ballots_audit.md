# 2013 Epsom & Ewell issued-ballots provenance audit

## Scope and method

The Surrey County Council individual result pages used for the 2013 baseline do
not publish `ballot_papers_issued`. This audit reviewed the official Epsom &
Ewell Borough Council election-results index and each of its five listed Surrey
County Council division pages.

Each source page explicitly names **Surrey County Council Elections — Thursday,
2 May 2013**, the division, every candidate, their votes, vote share, outcome,
total votes, ballot papers issued and rejected ballots. For integration, the
complete candidate-vote list was compared with the existing Surrey official
candidate records. All five lists match exactly.

## Verified supplementary values

| Division | Issued ballot papers | Official Epsom & Ewell source |
| --- | ---: | --- |
| Epsom Town & Downs | 3,733 | [result page](https://democracy.epsom-ewell.gov.uk/mgElectionAreaResults.aspx?ID=500000001) |
| Epsom West | 3,060 | [result page](https://democracy.epsom-ewell.gov.uk/mgElectionAreaResults.aspx?ID=500000002&RPID=0) |
| Ewell | 3,282 | [result page](https://democracy.epsom-ewell.gov.uk/mgElectionAreaResults.aspx?ID=500000003) |
| Ewell Court, Auriol & Cuddington | 3,466 | [result page](https://democracy.epsom-ewell.gov.uk/mgElectionAreaResults.aspx?ID=500000004&RPID=0) |
| West Ewell | 2,813 | [result page](https://democracy.epsom-ewell.gov.uk/mgElectionAreaResults.aspx?ID=500000005) |

The [official Epsom & Ewell election index](https://democracy.epsom-ewell.gov.uk/mgElectionElectionAreaResults.aspx?EID=500000001&RPID=0)
lists exactly these five 2013 Surrey County Council divisions.

## Source limitation and storage decision

None of the five Epsom & Ewell pages publishes an electorate value. This is a
source limitation, not a value to infer. The issued-ballot values are stored as
`secondary_division_ballot_papers_issued`, with a source-specific note and
complete candidate-vote-list cross-check. They do not fill Surrey's official
`ballot_papers_issued` field and do not change division completeness.
