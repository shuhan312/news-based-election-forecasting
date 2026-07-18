# Surrey Geographic Crosswalk Resolution Report

## Resolution outcome

- Relationships reviewed: 167
- Accepted direct mappings: 24
- Partial crosswalk relationships: 75
- Not comparable relationships: 43
- Requires-review relationships: 25
- Crosswalk topology components: 10
- Historical features generated: False

## Direct mapping and partial crosswalk are different

Only the existing accepted_direct rows are strict one-to-one analytical matches.

A partial crosswalk preserves split, merged and many-to-many GIS topology. It never represents a direct electoral mapping.

## Partial crosswalk topology

- many_to_many: 37
- many_to_one: 19
- one_to_many: 19

## Structured unresolved reasons

- non_structural_insufficient_overlap: 43
- one_to_one_direct_criteria_unmet: 25
- structural_partial_crosswalk: 75

## Weighting position

No election-specific electorate, population or residential crosswalk source has been audited for these historical divisions and 2026 wards. Area overlap is retained as GIS evidence only and must not be treated as a vote-redistribution weight.

No numeric electorate, population, residential or area weight has been created.

## Downstream protection

- Do not redistribute historical votes through a partial crosswalk.
- Do not calculate vote-share change through a partial crosswalk.
- Do not transfer candidate history, incumbency or previous-winner status through a partial crosswalk.
- Do not create a numeric weight unless a separately audited source explicitly supports it.
