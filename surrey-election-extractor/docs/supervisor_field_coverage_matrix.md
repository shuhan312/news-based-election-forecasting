# Supervisor field coverage matrix

**Scope:** current release field coverage matrix, recomputed against the
generated 24-event master payload and tied to it by
`tests/test_release_documentation.py`.

**Denominators:** 24 elections, 343 areas and 1,992 candidate rows.

**Lookup coverage:** 40 standard parties and all 81 current 2026 wards. The
ward lookup contains 24 approved direct mappings, 36 changed-boundary blocked
rows and 21 rows with insufficient validated weighting evidence.

This matrix maps every election field requested by the supervisor to the
current source-preserving master database. `Official` means published on the
result source; `supplementary`, `derived` and `analysis` never overwrite an
official value.

| Supervisor-required field | Current coverage | Release interpretation |
| --- | ---: | --- |
| Election name, date and type | 24/24 events | Complete. |
| Authority | 24/24 events | Complete at election level. |
| Division or ward name | 343/343 areas | Complete. |
| Number of seats available | 315 official; 28 supplementary; 343 analysis-ready | Complete analytical structure with split provenance. |
| Candidate name | 1,992/1,992 published and 1,992/1,992 separately standardised | Published wording is retained unchanged. Standard display names use only explicit surname-comma, Unicode and whitespace rules and never establish person identity. |
| Party name exactly as published | 1,991/1,992 | One blank official 2013 cell remains `NULL`. |
| Standardised party name | 1,992/1,992 | The one blank published label retains official NULL and uses the separate analytical label `No published party label`. The three observed UKIP labels share `UK Independence Party` as their standard name, while every original label is retained and Reform UK remains separate. |
| Established, emerging, local or independent | 1,992/1,992 | The blank-label candidate is analytically unaffiliated/independent under Electoral Commission nomination guidance. |
| Votes received | 1,992/1,992 | Complete official candidate votes. |
| Vote share | 1,986 official; 1,992 analysis-ready | Six governed Epsom West 2015 calculations remain separate. |
| Final position | 0 official; 1,992 derived | Competition rank is available for analysis; all official cells remain `NULL`; 8 rows are tied. |
| Elected, Yes or No | 1,992/1,992 | Recoded only from explicit official Outcome. |
| Winning candidate and party | 262 single-winner summaries; elected-name/party lists for 343/343 | Multi-member wards retain both elected candidates and do not receive an arbitrary single winner. |
| Winning margin | 0 official; 343 analysis-ready | 262 runner-up gaps plus 81 explicitly labelled final-seat cutoff gaps. |
| Electorate | 341/343 official | Two documented unsupported source values. |
| Ballot papers issued | 256 official; 340 supported | Three documented unsupported areas after permitted layers. |
| Turnout | 257 official; 340 supported | Three documented unsupported areas after permitted layers. |
| Rejected ballots | 341 official; 342 supported | One documented unsupported area after permitted layers. |
| Previous winning party | 205/343 areas | Only approved historical relations. |
| Previous party vote share | 1,042/1,992 candidate rows | Exact published current-party label in an approved predecessor; not a reconstructed party total. |
| Change in vote share | 796/1,992 candidate rows | Outcome diagnostic, prohibited from the no-news predictor. |
| Candidate previously stood, Yes or No | 360 True; 1,274 False; 358 Unknown | Unknown is confined to the 2013 first-period boundary. |
| Incumbent candidate, Yes or No | 116 Yes; 1,518 No; 358 Unknown | Unknown is confined to 2013; later values use the complete pre-election roster. |
| Incumbent party, Yes or No | 171 Yes; 631 No; 1,190 Unknown | Unknown preserves unavailable or non-comparable historical geography. |
| First appearance of party in area, Yes or No | 1,060/1,992 | First observed exact label in an approved project lineage, not historical origin. |
| Source URL | 1,992/1,992 candidate rows | Complete official candidate provenance. |
| Notes | 1,710 populated; 282 `NULL` | `NULL` means no row-specific limitation was recorded, not missing provenance. |

## Interpretation rules

1. Coverage is not maximised by overwriting official `NULL` values.
2. Analysis-ready values must retain their evidence layer and status.
3. `Unknown` is distinct from `No` for identity and incumbency fields.
4. 2013 is the first-period boundary for lagged person-level features because
   the supervisor's extraction scope begins in 2013.
5. The 2026 two-member wards are never treated as unchanged single-member
   divisions unless a separate limited historical permission explicitly allows
   the stated feature.
6. Reform UK remains separate from UKIP. The exact published UKIP variants are preserved but share one reviewed standard party name.
7. Reform UK's UKIP relationship is historical context only; it never transfers party identity, candidates or votes.
8. Every 2026 ward appears in the geographic lookup, but only the 24 permission-approved direct relationships can supply historical values.
