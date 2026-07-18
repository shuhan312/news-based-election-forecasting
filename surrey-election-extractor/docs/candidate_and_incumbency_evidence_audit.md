# Candidate History and Incumbency: Official Evidence Audit

## Purpose

This audit defines reproducible candidate-history and incumbency fields without
fuzzy identity matching. It is separate from division continuity and the
2021-to-2026 geographic permission audit.

## Evidence rule

`candidate_previously_stood` means that the candidate appeared in an earlier
audited Surrey County Council election within the project's 2013--2026
observation window. After the complete 2013 candidate tables establish that
window, every later row is checked against every earlier official candidate
table available before its polling date.

The deterministic route normalises only the documented 2013 `Surname, Given`
presentation and case, accents and punctuation. It requires every complete
name token to agree. It does not remove initials, accept shortened names,
calculate similarity, use party membership as identity evidence, or allow a
same-day result to enter another event's history. Therefore:

- `True` means the same complete published identifier occurs on a separate,
  earlier official result page;
- `False` means that identifier is absent from the complete earlier in-scope
  official candidate universe;
- `NULL` means no earlier complete observation window exists, or that an exact
  complete-name collision cannot be resolved by the chronological official
  officeholder roster.

Three stronger reviewed official routes can override a collision and are
recorded in `config/candidate_continuity_evidence.json`:

1. **Direct member-profile route.** A public Surrey County Council profile has
   a stable numeric `UID` and directly links the exact target and earlier
   official result pages.
2. **Multi-source official route.** A public profile with a stable `UID`, the
   exact target result page and at least one dated earlier official result page
   are reviewed together. Each source must preserve the same exact published
   candidate name and is retained in the evidence register. An official borough
   declaration or nomination document may be used for the earlier source when
   its public authority, URL and candidate-name evidence are recorded.
3. **Official Council-record route.** The exact prior and target official
   result pages are reviewed with a dated official Council record that
   explicitly names the person as taking the relevant County Council office.
   The recorded term start and Council-record date must both predate the target
   election. This route does not invent a member-profile URL or UID.

`incumbent_candidate = True` is stricter under every route: the reviewed
official evidence must establish a term start before the target election date,
and the target row must retain the reviewed published party label.

No missing profile, similar or partial name, party label, division name, winner
status or vote total is treated as identity evidence. Candidate-history `No`
is supported only by absence from the complete chronological candidate-result
universe; candidate incumbency uses the separate complete councillor roster.

## Verified person-level records

| Target election | Division | Candidate row | Verified fields | Official evidence |
| --- | --- | --- | --- | --- |
| 2017 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | Surrey [member profile UID 192](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192), which records a term from 06/05/1993 and lists the 2013, 2017 and 2021 elections; linked [2013 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=101) and [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187). |
| 2021 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | The same profile directly links the earlier 2013 and 2017 results and the [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272). |
| 2021 | Farnham Central | Andy MacLeod | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | Reviewed multi-source evidence: Surrey [member profile UID 2251](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=2251) gives a term from 08/05/2017 and lists the elections; the exact official [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=198) and [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=283) both publish Andy MacLeod for Farnham Residents. |
| 2021 | Woking South West | Ayesha Azad | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | Surrey [member profile UID 2216](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=2216) gives a term beginning 08/05/2017 and lists the 2017 and 2021 elections; the exact official [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=252) and [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=336) both publish Ayesha Azad for Conservative as Elected. |
| 2021 | Warlingham | Becky Rush | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | Reviewed Council-record evidence: official [2019 by-election result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=256), [Council minutes](https://mycouncil.surreycc.gov.uk/documents/s55233/Minutes%20Public%20Pack%2005022019%20Council.pdf) dated 5 February 2019, and the exact [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=327). The minutes explicitly identify Becky Rush as the new County Councillor after the 31 January 2019 by-election. |
| 2021 | The Byfleets | Amanda Jayne Boote | `candidate_previously_stood = True`; `incumbent_candidate_yes_no = Yes` | Reviewed Council-record evidence: official [2018 by-election result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=255), [Council minutes](https://mycouncil.surreycc.gov.uk/ieListDocuments.aspx?CId=121&MId=5844) dated 11 December 2018, and the exact [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=323). The minutes explicitly identify Amanda Jayne Boote as the new County Councillor after the 6 December 2018 by-election. |

The [official 2017 County Council minutes](https://mycouncil.surreycc.gov.uk/documents/s38257/item%2002%20-%20MinutesAGM230517.pdf)
also describe Hazel Watson as Surrey's longest-serving County Councillor and
state that she was first elected in 1993. This corroborates, but does not
replace, the profile-to-result-link evidence.

## Field decisions

| Field | Current decision | Reason |
| --- | --- | --- |
| Previous winner's candidate vote share | Already materialised for 184 approved division references. | It comes from a prior official candidate row explicitly marked `Elected`; it is not a party-total share. |
| Previous party vote share | Remains `NULL`. | No audited division-level party-total series exists; candidate shares are not aggregated. |
| Candidate previously stood | `True/False` after the 2013 observation boundary; `NULL` for 2013 or an unresolved exact-name collision. | Every earlier audited official candidate table is searched chronologically using complete-name deterministic linkage. A unique pre-election official roster entry or stronger reviewed profile/Council evidence can resolve a collision. |
| Incumbent candidate, Yes or No | `incumbent_candidate_yes_no = Yes` only where reviewed official evidence establishes a term before the target election; otherwise `Unknown`. | The separate boolean/NULL evidence value is retained for machine use. A repeated name or unsuccessful search cannot prove `No`. |
| Incumbent party, Yes or No | `incumbent_party_yes_no = Yes/No` when an approved, comparable single-member history identifies the prior official winning party; otherwise `Unknown`. | This is an area/party comparison, not a person-identity claim. It uses exact published labels and does not transfer incumbency across changed or multi-member geography. |
| Incumbent party name | `incumbent_party_name` retains the exact prior winning-party label whenever the party Yes/No comparison is decidable. | Keeping the name separate prevents a party label from being mistaken for the supervisor's required Yes/No answer. |
| Change in vote share | Available separately for approved exact-label single-member comparisons. | It is a post-election diagnostic, never candidate-identity evidence or a no-news predictor. Party-total reconstruction and cross-boundary swing remain prohibited. |

## Complete pre-election roster method

The supervisor-facing `incumbent_candidate_yes_no` is now determined from a
chronological official roster rather than from success or failure in finding an
individual profile. The complete 2013, 2017 and 2021 results establish each
81-member Council; every audited intervening by-election removes the vacant
seat and installs the newly elected official winner. Each later event is then
compared with the roster that existed immediately before its polling date.

This permits both `Yes` and `No` after 2013. `No` means absent from a complete
official pre-election roster, not “no profile found”. Same-day elections use the
same opening snapshot, and the 2026 East/West results do not overwrite the
continuing Surrey County Council roster. The 2013 candidate rows remain
`Unknown` because a complete audited 2009 roster is not present in the project.

The chronological update also resolves repeated complete names without a
manual guess. Two 2021 official result rows publish `David John Lewis`, but the
2025 Camberley West by-election replaces one of those seats before the 2026
poll. The remaining Cobham officeholder is therefore unique in the official
pre-election roster.

## Candidate-history boundary

The classification is complete for the declared 2013--2026 project window; it
is not a claim about candidatures before 2013 or elections outside Surrey County
Council. The 2013 rows therefore remain first-period `NULL`, rather than being
mislabelled `False` because 2009 is outside the extracted scope. An unresolved
exact-name collision also remains `NULL` unless the chronological official
roster, a stable official profile or a dated Council record identifies the
person. In the current payload the roster resolves the only post-2013 collision,
so all 358 remaining `NULL` values are 2013 first-period records. These are
explicit design boundaries, not unrecorded search failures.
