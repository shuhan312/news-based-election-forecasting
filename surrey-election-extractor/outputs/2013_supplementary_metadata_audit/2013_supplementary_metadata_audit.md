# 2013 Surrey County Council Supplementary Metadata Audit

## Scope and data principle

- This is a pre-extraction source and policy audit only. No 2013 candidate extraction or metadata integration was run.
- Official Surrey result-page fields remain official. Secondary evidence is stored separately and never overwrites them.

## Source evaluation

### Surrey News: Election results declared

- URL: https://news.surreycc.gov.uk/2013/05/03/election-results-special/
- Geographic level: Surrey-wide summary and named divisions
- Fields: overall_turnout, division_turnout
- Evidence: The votes have been counted in all 81 divisions for the 2013 Surrey County Council elections; Turnout 30%. The article also gives named division result entries with turnout, for example ‘RESULT – WORPLESDON’ followed by ‘Turnout 32%’.
- Reliability: High: published by Surrey County Council.
- Decision: Use the 30% value only as supplementary election-level turnout. A future division-by-division evidence audit may use named turnout entries as supplementary metadata, but this audit does not bulk-load them.

### Electoral Commission: Results and turnout at the May 2017 England local elections

- URL: https://www.electoralcommission.org.uk/research-reports-and-data/our-reports-and-data-past-elections-and-referendums/results-and-turnout-may-2017-england-local-elections
- Geographic level: Surrey-wide
- Fields: overall_turnout
- Evidence: Table 3.2 lists Surrey ballot-box turnout as 30.0% for 2013 and 35.8% for 2017.
- Reliability: High: statutory electoral authority; independently corroborates the Surrey Council rounded 30% summary.
- Decision: Use as corroborating supplementary election-level evidence only; it does not identify individual Surrey divisions.

### Woking Borough Council: Election of Councillors

- URL: https://www.woking.gov.uk/sites/default/files/documents/council-and-democracy/elections/ElectionResults/resultsscc.pdf
- Geographic level: Named Woking Surrey County Council divisions only
- Fields: division_turnout, ballot_papers_issued, electorate, seats, candidate_results
- Evidence: The PDF gives named division summaries, for example Knaphill & Goldsworth West: ‘Vacant Seats: 1 Electorate: 11,021 Ballot Papers Issued: 3,642 Turnout: 33.05%’.
- Reliability: High for the named Woking divisions; not a Surrey-wide source.
- Decision: A future exact division-name match may store turnout or ballot papers issued as supplementary division metadata for named Woking divisions only. It must not replace the official Surrey result-page fields or be generalised to other divisions.

### Wikipedia: 2013 Surrey County Council election

- URL: https://en.wikipedia.org/wiki/2013_Surrey_County_Council_election
- Geographic level: Election-wide and division tables
- Fields: election_date, county_seat_total, party_summary, division_turnout
- Evidence: The page describes the election date and presents election and division summaries.
- Reliability: Lower than Electoral Commission and official council publications.
- Decision: Do not use. Higher-priority official sources exist for the audited election-level information, and the project policy does not permit Wikipedia for division-level replacement.

## Field policy

### election_name (election)

- Official status: Available from the configured official archive context.
- Can supplement: False
- Storage: official election-level configuration field
- Policy: Do not add a secondary value.

### election_date (election)

- Official status: Published in the official archive/result-page context as 2 May 2013.
- Can supplement: False
- Storage: official election-level field
- Policy: Do not add a secondary value.

### authority (election)

- Official status: Published by official result pages as Surrey County Council; absent from the current declarative configuration.
- Can supplement: False
- Storage: official election-level field when sourced from an official page
- Policy: Do not treat an external source as a replacement for the missing configuration entry.

### overall_turnout (election)

- Official status: Not published as an overall value in representative individual official result pages.
- Can supplement: True
- Storage: supplementary election metadata field
- Policy: Store only as secondary_election_turnout with separate source URL, evidence text, geographic level and confidence. Do not copy it to any division turnout field.

### turnout (division)

- Official status: Not published in the three representative official Surrey result-page Voting Summary tables.
- Can supplement: conditionally
- Storage: supplementary division metadata field, otherwise remain missing
- Policy: Only store a value after the source identifies the same division and preserves an exact supporting passage. Never propagate the 30% Surrey-wide turnout to divisions.

### ballot_papers_issued (division)

- Official status: Not published in the three representative official Surrey result-page Voting Summary tables.
- Can supplement: conditionally
- Storage: supplementary division metadata field, otherwise remain missing
- Policy: The Woking document may support named Woking divisions after exact matching. No Surrey-wide value or inferred calculation is permitted.

### rejected_ballots (division)

- Official status: Published in the representative official Surrey result-page Voting Summary tables.
- Can supplement: False
- Storage: official division-level field
- Policy: Retain the published official value; any unreported division remains missing.

### seats (division)

- Official status: Published in the representative official Surrey result-page Voting Summary tables.
- Can supplement: False
- Storage: official division-level field
- Policy: Retain the published official value; never infer seats from the election year or candidate count.

### candidate_name, original_party_name, votes, vote_share, outcome (candidate)

- Official status: Published in representative official Surrey result-page candidate tables.
- Can supplement: False
- Storage: official candidate-level fields
- Policy: Never replace official candidate-level values with a secondary source.

## Approved supplementary policy

- Election-level turnout: 30% (High confidence), stored only as `secondary_election_turnout`.
- Restriction: Election-wide only; not copied to any division record.
- Candidate-level values remain official-result-page data only. No secondary candidate source is approved for replacement or completion.
- Wikipedia was evaluated but is not used because higher-priority official Council and Electoral Commission sources are available. It must not supply division-level replacements.

## Recommendation

If supplementary division metadata is later required, perform a separate named-division evidence audit before integration. Do not start full 2013 extraction as part of this audit.
