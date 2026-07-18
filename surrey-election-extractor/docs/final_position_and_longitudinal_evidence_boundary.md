# Final Position and Longitudinal Evidence Boundary

## Purpose

This note records the evidence boundary for the two supervisor-required areas
that cannot be populated by a simple candidate-table parse: official
`final_position` and longitudinal candidate history.  It is read-only
documentation; it does not alter extracted official values.

## Final position

The final-position audit inspects candidate-table *headers*, not the visual
order of candidate rows.  A result can support `final_position` only when the
official source explicitly publishes a field such as `Final position`,
`Position`, `Rank` or `Placing`.

- The completed 2017 and 2021 all-division audit found the ordinary headers
  `Election Candidate`, `Party`, `Votes`, `%` and `Outcome`, with no official
  position field.
- The official 2013 county results summary, the 2026 East/West result-page
  format, and checked official by-election declarations use the same
  candidate/votes/outcome pattern rather than an official ranking column.
- The Electoral Commission's declaration guidance requires publication of
  candidate names, elected candidates, votes and rejected ballots; it does
  not make a candidate rank a required declaration field.

The audit script now covers all five principal elections in the master
database.  It returns an **inconclusive** result if even one intended official
page cannot be inspected in that run.  Therefore, a temporary website block
cannot be used as evidence that final position is absent.

`final_position` remains `NULL`: it is never calculated by sorting votes, and
candidate display order is never treated as a rank.

## Longitudinal fields

The master database exposes historical values only where the geography and the
source both support the relation.

- `previous_winning_party` and the previous winning candidate's published
  share are available for 184 permitted relations: 81 from 2013 to 2017, 81
  from 2017 to 2021, and 22 from 2021 to 2026.
- `previous_party_vote_share` and `change_in_vote_share` remain `NULL` because
  the source tables publish candidate shares, not a verified party-total
  series.  Reconstructing a party total would be an unrecorded calculation.
- `candidate_previously_stood`, `incumbent_candidate` and `incumbent_party`
  are positive-only fields. They use either the direct profile route, or a
  reviewed multi-source official route that retains a stable profile, the exact
  target result page and an earlier exact result page. Incumbency additionally
  requires a published term start before the election. The reviewed register
  currently contains three verified rows; none was created by automated name
  matching.

This method deliberately does not join candidates by name, party or area.  A
missing entry means **not yet verified**, not `No`.

## Sources

- [Electoral Commission: declaration of result guidance](https://www.electoralcommission.org.uk/guidance-candidates-and-agents-local-government-elections-england/verification-and-count/declaration-result)
- [Surrey County Council Election 2013 official results summary](https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&RPID=0&V=1)
- [East Surrey Council 2026: Addlestone official result page](https://www10.surreycc.gov.uk/electionmap/EastSurrey/387)
- [Epsom West 2015 official declaration of result](https://www.epsom-ewell.gov.uk/sites/default/files/documents/council/elections-and-voting/SCCDeclarationofResults19Nov2015.pdf)
- [Hazel Valerie Ann Watson: official Surrey member profile](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192)

## Conclusion

The current design is intentionally conservative.  It can accept more
longitudinal or rank evidence in the future, but only when an authoritative
source supplies a field or a direct, reproducible linkage.  It does not claim
that no unindexed archive could ever exist.
