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
- `previous_party_vote_share` is materialised only for approved exact-label
  references. `change_in_vote_share` is then available as a post-election
  percentage-point diagnostic for comparable single-member contests. It is
  never a no-news predictor, and multi-member or altered-boundary party swing
  remains prohibited.
- `candidate_previously_stood` is a tri-state, in-scope candidature-history
  field. After the complete 2013 candidate result establishes the observation
  window, it uses exact complete-name deterministic linkage across all earlier
  audited official result tables. It never drops name tokens or uses fuzzy
  similarity. Absence from that complete prior universe supports `False`;
  2013 remains `NULL`. An exact-name collision requires resolution through the
  chronological official officeholder roster, a stable official profile or a
  dated Council record.
- `incumbent_candidate` and its supervisor-facing Yes/No/Unknown field use the
  separate chronological elected-member roster. `incumbent_party_yes_no` uses
  an approved comparable historical area and exact published party labels.

Candidate-history `NULL` therefore means a declared first-period or identity
collision boundary, not an unreported failed search. Candidate-history `No`
means no exact complete published identifier exists anywhere in the complete
earlier in-scope official candidate universe; it is not a claim about elections
before 2013 or outside Surrey County Council.

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
