# Historical Reference Permission Audit

## Purpose

This audit separates a reviewed GIS relationship from permission to transfer
electoral history. A spatial relationship can be technically suitable for
comparison while still requiring an explicit research decision before previous
winner, turnout or party-history fields are exposed in a baseline dataset.

## Current reviewed crosswalk state

The current geographic crosswalk resolution contains 167 retained relationships:

| Status | Relationships | Historical-reference permission |
| --- | ---: | --- |
| `accepted_direct` | 22 | 0 explicitly permitted |
| `partial_crosswalk_available` | 75 | blocked |
| `not_comparable` | 43 | blocked |
| `requires_review` | 27 | blocked |

All 22 `accepted_direct` rows currently set
`previous_winner_allowed=false`. They remain valuable, traceable GIS evidence,
but they do not currently authorise a transfer of previous election results.

## Applied rule

The historical baseline now exposes a direct historical reference only when one
and only one matching row has both:

1. `analytical_status=accepted_direct`; and
2. `previous_winner_allowed=true`.

Without both conditions, previous winner, previous turnout and area-specific
party-history fields remain `NULL`. Candidate identity, incumbent status and
vote-share change remain blocked even if the permission is later granted:
they require their own evidence and are not derived from matching names or GIS
overlap.

## Required future decision

Any future approval must be recorded against the exact mapping ID with the
reviewer, review date and a concise evidence rationale. It must not be inferred
from a ward-name match, overlap percentage, election year or candidate name.
Until that decision exists, keeping the fields unavailable is the reproducible
and source-preserving outcome.
