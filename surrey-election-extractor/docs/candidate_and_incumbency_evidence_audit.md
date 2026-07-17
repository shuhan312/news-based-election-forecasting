# Candidate History and Incumbency: Official Evidence Audit

## Purpose

This audit tests whether the currently empty personal-history fields can be
filled without name matching. It is separate from division continuity and the
2021-to-2026 geographic permission audit.

## Evidence rule

A candidate receives `candidate_previously_stood = True` and
`incumbent_candidate = True` only when all of the following are recorded in
`config/candidate_continuity_evidence.json`:

1. A public Surrey County Council member profile has a stable numeric `UID`.
2. That profile directly links to the exact official result-page ID for the
   published candidate row.
3. The same profile directly links to at least one dated earlier official
   election-result page.
4. The profile's published term start is before the target election date.
5. The target candidate row has the exact reviewed division and published party
   label recorded in the evidence register.

No missing profile, similar name, party label, division name, winner status or
vote total is treated as evidence that a candidate previously stood or was not
an incumbent. Those records remain `NULL`.

## First verified records

| Target election | Division | Candidate row | Verified fields | Official evidence |
| --- | --- | --- | --- | --- |
| 2017 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate = True`; `incumbent_party = Liberal Democrats` | Surrey [member profile UID 192](https://mycouncil.surreycc.gov.uk/mgUserInfo.aspx?UID=192), which records a term from 06/05/1993 and lists the 2013, 2017 and 2021 elections; linked [2013 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=101) and [2017 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=187). |
| 2021 | Dorking Hills | Hazel Valerie Ann Watson | `candidate_previously_stood = True`; `incumbent_candidate = True`; `incumbent_party = Liberal Democrats` | The same profile directly links the earlier 2013 and 2017 results and the [2021 result](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=272). |

The [official 2017 County Council minutes](https://mycouncil.surreycc.gov.uk/documents/s38257/item%2002%20-%20MinutesAGM230517.pdf)
also describe Hazel Watson as Surrey's longest-serving County Councillor and
state that she was first elected in 1993. This corroborates, but does not
replace, the profile-to-result-link evidence.

## Field decisions

| Field | Current decision | Reason |
| --- | --- | --- |
| Previous winner's candidate vote share | Already materialised for 184 approved division references. | It comes from a prior official candidate row explicitly marked `Elected`; it is not a party-total share. |
| Previous party vote share | Remains `NULL`. | No audited division-level party-total series exists; candidate shares are not aggregated. |
| Candidate previously stood | `True` only for the reviewed official-profile records above; otherwise `NULL`. | The register proves a person-level link without relying on a name match. |
| Incumbent candidate | `True` only for the reviewed official-profile records above; otherwise `NULL`. | The profile provides both an earlier official election link and a term predating the target election. |
| Incumbent party | Populated only with `incumbent_candidate = True` and preserves the target row's original published party label. | It makes no claim about a past party affiliation or party switch. |
| Change in vote share | Remains `NULL`. | Party-total reconstruction and cross-boundary swing remain prohibited. |

## Limitation and next extension

This first register is deliberately small: it demonstrates the strict evidence
path with two independently verifiable rows. It does not claim that other
candidates were new or non-incumbent. Future additions require the same direct
official profile-to-result evidence and must be reviewed one record at a time.
