# Surrey County Council Election 2026 Compatibility Audit

- Compatibility status: `requires_changes`
- Candidate and Voting Summary structures are compatible in the sampled official pages, but the existing discovery stage does not support the separate 2026 www10.surreycc.gov.uk map indexes.

## Official map indexes

### surrey-county-council-2026-east-surrey
- Index: https://www10.surreycc.gov.uk/electionmap/eastSurrey/
- Declared wards: 36 of 36
- Result links: 72 raw; 36 unique; 36 repeats removed; 0 invalid.
- Candidate headers: %, Election Candidate, Outcome, Party, Votes.
- Voting Summary fields in every sampled page: {'number_of_seats': True, 'total_votes': True, 'electorate': True, 'ballot_papers_issued': True, 'ballot_papers_rejected': True, 'turnout': True}.
- Official Seats values sampled: ['2', '2'] (from the Voting Summary only).
- Final position: Official final_position was not observed in the sampled candidate tables and must remain NULL; no ranking is calculated from votes.

### surrey-county-council-2026-west-surrey
- Index: https://www10.surreycc.gov.uk/electionmap/WestSurrey/
- Declared wards: 45 of 45
- Result links: 90 raw; 45 unique; 45 repeats removed; 0 invalid.
- Candidate headers: %, Election Candidate, Outcome, Party, Votes.
- Voting Summary fields in every sampled page: {'number_of_seats': True, 'total_votes': True, 'electorate': True, 'ballot_papers_issued': True, 'ballot_papers_rejected': True, 'turnout': True}.
- Official Seats values sampled: ['2', '2'] (from the Voting Summary only).
- Final position: Official final_position was not observed in the sampled candidate tables and must remain NULL; no ranking is calculated from votes.

## Required changes before extraction

- Add a narrowly validated 2026 map-index discovery route for the two configured www10.surreycc.gov.uk indexes, deduplicating published result links by EID and ID.

## Confirmed boundaries

- No modification was made to discovery.py, official_source.py, extraction.py, validation.py or master_database.py.
- No 2026 candidate records, workbook rows or master-database rows were created.
- Seats, turnout, ranking and winners were not inferred.

## Recommendation

Implement and test only the two-index 2026 discovery adapter, then rerun this compatibility audit before approving a separate East/West extraction.
