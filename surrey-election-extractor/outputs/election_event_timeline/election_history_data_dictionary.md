# Election Event Timeline and Baseline Preparation Data Dictionary

| Field | Meaning | Provenance | Missing/blocked rule |
| --- | --- | --- | --- |
| election_events.election_id | Canonical event identifier | source reported / deterministically derived | Never merged across events. |
| election_events.candidate_row_count | Published candidate rows available for an event | deterministically derived | NULL for catalogued by-elections without verified candidate-result evidence. |
| canonical_candidate_results.original_party_name | Exact published party wording | source reported | Never overwritten by standardisation. |
| canonical_candidate_results.standardised_party_name | Reviewed lookup label | manually confirmed | NULL when no approved lookup exists; Reform UK and UKIP stay separate. |
| election_chronology.previous_election_event_id | Prior event in the same valid geographic identity | deterministically derived | NULL for unavailable mappings or same-date ambiguity. |
| safe_enrichment.candidate_appeared_before | Candidate appearance history | unavailable | No name-only matching; explicit identity evidence is required. |
| safe_enrichment.party_history | Party appearance and previous contests | deterministically derived | Uses approved standard-party labels only. |
| safe_enrichment.number_of_candidates | Candidate count in published candidate-result evidence | deterministically derived | NULL when candidate rows are unavailable. |
| safe_enrichment.previous_winner | Prior winner | unavailable | Blocked pending approved geographic comparison rules. |
| safe_enrichment.vote_share_change | Change in party or candidate vote share | unavailable | Blocked; no geographic redistribution or comparison is performed. |
| safe_enrichment.incumbency | Incumbency or predecessor transfer | unavailable | Blocked; no candidate history crosses partial or unresolved mappings. |

Official source values are never overwritten. `source_reported`, `deterministically_derived`, `manually_confirmed` and `unavailable` are distinct provenance states. Partial crosswalk, not-comparable and requires-review geographic rows cannot generate chronology links, candidate history, incumbency, previous winners or vote comparisons.
