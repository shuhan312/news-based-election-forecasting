# Surrey County Council Election 2026 Compatibility Audit

- Compatibility status: `compatible`
- The implemented 2026 map-index discovery adapter produces the complete published East and West ward URL sets, and representative official result pages are compatible with the existing candidate, Voting Summary, multi-seat and layered-completeness contracts.

## Official map indexes

### surrey-county-council-2026-east-surrey
- Index: https://www10.surreycc.gov.uk/electionmap/eastSurrey/
- Declared wards: 36 of 36
- Result links: 72 raw; 36 unique; 36 repeats removed; 0 rejected.
- Candidate headers: %, Election Candidate, Outcome, Party, Votes.
- Voting Summary fields in every sampled page: {'number_of_seats': True, 'total_votes': True, 'electorate': True, 'ballot_papers_issued': True, 'ballot_papers_rejected': True, 'turnout': True}.
- Official Seats values sampled: ['2', '2'] (from the Voting Summary only).
- Final position: Official final_position was not observed in the sampled candidate tables and must remain NULL; no ranking is calculated from votes.

### surrey-county-council-2026-west-surrey
- Index: https://www10.surreycc.gov.uk/electionmap/WestSurrey/
- Declared wards: 45 of 45
- Result links: 90 raw; 45 unique; 45 repeats removed; 0 rejected.
- Candidate headers: %, Election Candidate, Outcome, Party, Votes.
- Voting Summary fields in every sampled page: {'number_of_seats': True, 'total_votes': True, 'electorate': True, 'ballot_papers_issued': True, 'ballot_papers_rejected': True, 'turnout': True}.
- Official Seats values sampled: ['2', '2'] (from the Voting Summary only).
- Final position: Official final_position was not observed in the sampled candidate tables and must remain NULL; no ranking is calculated from votes.

## Discovery and parsing compatibility

- surrey-county-council-2026-east-surrey: discovery output consumable by extraction = True; declared count matches discovery = True.
- surrey-county-council-2026-west-surrey: discovery output consumable by extraction = True; declared count matches discovery = True.

## Multi-seat and completeness compatibility

- surrey-county-council-2026-east-surrey: elected candidates observed per sampled page = [2, 2]; multiple-elected support observed = True.
- surrey-county-council-2026-west-surrey: elected candidates observed per sampled page = [2, 2]; multiple-elected support observed = True.
- Layered completeness compatible in sampled pages: True.

## Remaining risks

- This is a bounded diagnostic, not a full candidate extraction. All 2026 wards must still be processed independently before results are used.
- East and West outputs must remain separate from 2013, 2017 and 2021 until ward-boundary mapping is completed.
- Published local party wording requires a later explicit lookup; it must not be standardised or merged during this audit.

## Confirmed boundaries

- This audit used the implemented discovery.py map-index adapter but did not modify discovery.py, official_source.py, extraction.py, validation.py, completeness.py or master_database.py.
- No 2026 candidate records, workbook rows or master-database rows were created.
- Seats, turnout, ranking and winners were not inferred.

## Recommendation

Subject to separate authorisation, run the existing full pipeline independently for East Surrey and West Surrey. Keep the two 2026 outputs separate from the historical master database until old divisions and new wards have been mapped.
