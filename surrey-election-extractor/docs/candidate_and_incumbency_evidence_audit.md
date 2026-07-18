# Candidate History and Incumbency: Official Evidence Audit

## Purpose

This audit tests whether the currently empty personal-history fields can be
filled without name matching. It is separate from division continuity and the
2021-to-2026 geographic permission audit.

## Evidence rule

A candidate receives `candidate_previously_stood = True` only when one of two
reviewed official routes is recorded in
`config/candidate_continuity_evidence.json`:

1. **Direct member-profile route.** A public Surrey County Council profile has
   a stable numeric `UID` and directly links the exact target and earlier
   official result pages.
2. **Multi-source official route.** A public profile with a stable `UID`, the
   exact target result page and at least one dated earlier official result page
   are reviewed together. Each source must preserve the same exact published
   candidate name and is retained in the evidence register. An official borough
   declaration or nomination document may be used for the earlier source when
   its public authority, URL and candidate-name evidence are recorded.

`incumbent_candidate = True` is stricter under either route: the reviewed
profile must also publish a term start before the target election date, and the
target row must retain the reviewed published party label.

No missing profile, similar name, party label, division name, winner status or
vote total is treated as evidence that a candidate previously stood or was not
an incumbent. Those records remain `NULL`.

## First verified records

| Target election | Division | Candidate row | Verified fields | Official evidence |
| --- | --- | --- | --- | --- |
| 2017 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate = True`; `incumbent_party = Liberal Democrats` | Surrey [member profile UID 192](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192), which records a term from 06/05/1993 and lists the 2013, 2017 and 2021 elections; linked [2013 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=101) and [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187). |
| 2021 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate = True`; `incumbent_party = Liberal Democrats` | The same profile directly links the earlier 2013 and 2017 results and the [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272). |
| 2021 | Farnham Central | Andy MacLeod | `candidate_previously_stood = True`; `incumbent_candidate = True`; `incumbent_party = Farnham Residents` | Reviewed multi-source evidence: Surrey [member profile UID 2251](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=2251) gives a term from 08/05/2017 and lists the elections; the exact official [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=198) and [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=283) both publish Andy MacLeod for Farnham Residents. |

The [official 2017 County Council minutes](https://mycouncil.surreycc.gov.uk/documents/s38257/item%2002%20-%20MinutesAGM230517.pdf)
also describe Hazel Watson as Surrey's longest-serving County Councillor and
state that she was first elected in 1993. This corroborates, but does not
replace, the profile-to-result-link evidence.

## Field decisions

| Field | Current decision | Reason |
| --- | --- | --- |
| Previous winner's candidate vote share | Already materialised for 184 approved division references. | It comes from a prior official candidate row explicitly marked `Elected`; it is not a party-total share. |
| Previous party vote share | Remains `NULL`. | No audited division-level party-total series exists; candidate shares are not aggregated. |
| Candidate previously stood | `True` only for the reviewed direct-profile or multi-source official records above; otherwise `NULL`. | The register proves a person-level link without relying on automated name matching. |
| Incumbent candidate | `True` only where the reviewed profile also supplies a term predating the target election; otherwise `NULL`. | A repeated candidate name or a current role is not projected backwards as incumbency. |
| Incumbent party | Populated only with `incumbent_candidate = True` and preserves the target row's original published party label. | It makes no claim about a past party affiliation or party switch. |
| Change in vote share | Available separately for approved exact-label single-member comparisons. | It is a post-election diagnostic, never candidate-identity evidence or a no-news predictor. Party-total reconstruction and cross-boundary swing remain prohibited. |

## Limitation and next extension

This register remains deliberately small: it demonstrates the direct-profile
and multi-source official routes without treating repeated names as identity
proof. It does not claim that other candidates were new or non-incumbent.
Future additions must be reviewed one record at a time and retain their public
official source URLs and evidence notes.
