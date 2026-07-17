# Surrey election-data readiness audit

**Audit date:** 17 July 2026  
**Scope:** the reproducible 20-event master database. This is an election-data
audit only; it does not collect or classify news.

## Scope checked

- 20 election events: 2013, 2017 and 2021 County Council elections; East and
  West Surrey 2026 elections; and 15 catalogued County Council by-elections.
- 1,971 candidate rows and 339 division or ward rows.
- Official extraction, supplementary evidence, governed derived values and
  historical-reference permissions are assessed separately.

## Supervisor field coverage

| Required area | Current evidence position | Boundary retained by the database |
| --- | --- | --- |
| Election name, date, type and authority | 20/20 election events | Election configuration and official event sources are stored at election level, not incorrectly required on every candidate page. |
| Division or ward, candidate, published party, votes, outcome and source URL | 339/339 areas; 1,971/1,971 candidate rows | One 2013 official Party cell is blank and remains blank in the official column. |
| Standardised party and category | 1,970/1,971 rows | No standardisation is created for that blank official Party cell. Reform UK and UKIP remain distinct. |
| Candidate vote share | 1,965/1,971 rows | The six Epsom West 2015 by-election rows have published votes but no published percentages; no percentage is calculated into the official field. |
| Seats | 311 official plus 28 statutory supplementary records | The 28 supplementary values do not overwrite official `NULL` Seats values. |
| Electorate | 338/339 official areas | Staines South & Ashford West 2016 remains unresolved in the reviewed official and borough sources. |
| Ballot papers issued | 254 official areas; 338/339 have a separate official, supplementary or governed-derived value | Weybridge 2015 remains unresolved. Derived issued-ballot values require same-page official inputs and remain separate. |
| Rejected ballots | 337 official areas; one separate derived value | Weybridge 2015 remains unresolved. Reigate 2017 has a separately recorded calculation of `4,109 issued − 4,109 total votes = 0`; its official field remains `NULL`. |
| Turnout | 254 official plus 83 supplementary records | Weybridge 2015 and Haslemere 2019 remain unresolved in the reviewed source scope. |
| Total votes | 338 official plus one separate derived value | Coverage is complete without overwriting an official field. |
| Winning candidate and party | 258 single-winner areas; all 81 two-seat 2026 wards retain every official elected candidate rather than selecting one | Multi-member wards do not receive an arbitrary single winner. |
| Winning margin | 230 separately governed single-seat derived records | Official margin remains `NULL` because no dedicated official margin field is published. 81 multi-member wards and 28 2021 pages without official Seats are excluded. |
| Final position | No official position column in the audited formats | All values remain `NULL`; row display order and vote ordering are never converted to rank. |

## Historical and candidate-history fields

- 184 division relationships have explicit geographic or statutory permission:
  81 from 2013 to 2017, 81 from 2017 to 2021 and 22 from 2021 to 2026.
  These can expose prior winner, published winner share, turnout and electorate
  only as allowed by the reviewed permissions.
- `previous_party_vote_share` and `change_in_vote_share` remain unavailable.
  The source tables contain candidate shares, not a reviewed party-total series,
  and the geographic permissions prohibit party swing or vote redistribution.
- Two candidate rows have positive, official-profile-backed continuity and
  incumbency evidence. All other candidates remain `NULL`, rather than being
  matched by name.
- Exact-label party history is available for 942 candidate rows in approved
  direct lineages; the remainder are not asserted to be new or absent.

## Remaining values: decision boundary

The outstanding Weybridge, Staines and Haslemere values have been checked
against the identified County Council and relevant borough result/declaration
sources. They are retained as `NULL` because none of the reviewed sources
publishes a division-specific value that can be safely integrated. This does
**not** assert that an unindexed historic document cannot exist.

The review is recorded in
[the by-election supplementary metadata audit](by_election_supplementary_metadata_audit.md).
Any future value must be added as an official, supplementary or derived record
with its own source URL, evidence text, scope and validation; it must not
silently fill an official missing cell.

## Readiness conclusion

The database is ready as an auditable election-results baseline. The remaining
gaps are visible publication limits or deliberately prohibited inferences, not
silent extraction failures. The next data changes should be limited to a new
authoritative, division-specific source or a separately approved methodology;
they should not be based on candidate order, name matching, geography guesses
or unrecorded calculations.
