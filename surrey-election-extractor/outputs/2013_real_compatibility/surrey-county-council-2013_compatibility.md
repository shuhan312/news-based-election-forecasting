# Surrey County Council Election 2013 Compatibility Audit

- Compatibility status: `compatible`
- Scope: read-only archive discovery and three representative official result pages; no extraction was run.

## Configuration and archive

- Official archive: `https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&RPID=0` (accessible).
- `authority` is absent from the current configuration and is not filled by this audit; official result pages are the possible source location.

## Discovery

- Unique divisions: 81
- Raw links: 243; duplicates removed: 162; invalid/failed: 0.
- URL pattern: /mgElectionAreaResults.aspx.
- Existing discovery followed the official 2013 election-area index and its published Page parameters; duplicate result URLs were deduplicated by result ID.

## Result-page structure

- Candidate fields available in all sampled pages: {'candidate_name': True, 'original_party_name': True, 'votes_received': True, 'vote_share': True, 'outcome': True}
- Voting Summary availability in all sampled pages: {'number_of_seats': True, 'electorate': True, 'ballot_papers_issued': False, 'ballot_papers_rejected': True, 'turnout': False}
- Voting Summary difference: The representative 2013 Voting Summary pages do not publish ballot_papers_issued, turnout. These remain NULL at division level; no values are inferred.
- Final position: Official final_position was not observed and must remain NULL; no vote-based ranking is calculated.

## Party handling and completeness

- Published party examples: Conservative, UK Independence Party, Labour, Liberal Democrats, Official Monster Raving Loony Party.
- Original published wording varies by party. Preserve it unchanged; do not merge UK Independence Party/UKIP with Reform UK.
- Existing layered completeness can retain missing division-level official fields as NULL; no new candidate-level completeness rule is required.

## Recommendation

A later, separately approved extraction run can use the existing pipeline.
