# surrey-county-council-2013 Layered Completeness Report

- Election completeness: `complete`
- Before (legacy candidate records): {'complete': 0, 'incomplete': 358, 'search_failed': 0}
- Candidate complete: 357
- Candidate incomplete: 1
- Division complete: 0
- Division incomplete: 81
- Division missing fields: {'ballot_papers_issued': 81, 'turnout': 81}
- Secondary Seats values: 0
- Official Seats fields still missing: 0

## Interpretation

Layered assessment does not alter extracted records or their legacy extraction_status values. Candidate completeness excludes election metadata and division Voting Summary fields.

The report is generated from the existing extraction audit only; it does not rerun discovery or extraction and does not fill missing official values.
