# Surrey Final Position Provenance Audit

**Scope:** read-only inspection of official candidate result tables. No rankings were calculated, no candidate records were changed, and no extraction code was modified.

## 2017 Surrey County Council Election

- Divisions checked: 81
- Official result URLs checked: 81
- Page classifications: {'valid_election_result_page': 81}
- Candidate tables found: 81
- Candidate-table header patterns: {'Election Candidate | Party | Votes | % | Outcome': 81}
- Pages with an official final-position/rank/placing header: 0
- Conclusion: **B. Official final_position is not published in the checked candidate result tables and should remain NULL.**

Example checked URLs (the JSON report lists every checked official URL):
- Addlestone: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=173&RPID=454155221&XXR=0
- Ash: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=174&RPID=454155221&XXR=0
- Ashford: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=175&RPID=454155221&XXR=0

## 2021 Surrey County Council Election

- Divisions checked: 81
- Official result URLs checked: 81
- Page classifications: {'valid_election_result_page': 81}
- Candidate tables found: 81
- Candidate-table header patterns: {'Election Candidate | Party | Votes | % | Outcome': 81}
- Pages with an official final-position/rank/placing header: 0
- Conclusion: **B. Official final_position is not published in the checked candidate result tables and should remain NULL.**

Example checked URLs (the JSON report lists every checked official URL):
- Addlestone: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=258&RPID=453722837&XXR=0
- Ash: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=259&RPID=453722837&XXR=0
- Ashford: https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=260&RPID=453722837&XXR=0

## Overall conclusion

**B. Official final_position is not published in the checked 2017 or 2021 Surrey candidate result tables and should remain NULL.**

Candidate display order was observed but is not an official rank field and was not converted into final position.
