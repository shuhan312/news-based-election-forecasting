# Surrey election-data readiness audit

**Audit date:** 18 July 2026

**Authoritative input:** generated 24-event master payload

**Scope:** election extraction, governed analytical fields and the boundary to
the no-news baseline. News collection and modelling are out of scope.

## Release snapshot

> Correction (2026-08-24): the snapshot bullets originally read 20 events /
> 15 by-elections; this understated the release. The audit's own authoritative
> 24-event master payload and 205-reference total already reflect 19
> by-elections, and the bullets are corrected to match.
>
> Correction (2026-08-27): the field table and no-news boundary below are
> refreshed to the current 24-event payload (343 areas, 1,992 candidate
> rows); earlier versions retained figures from the 339-area / 1,971-row
> release.

- 24 election events: 2013, 2017 and 2021 principal elections; separate East
  and West Surrey 2026 elections; and all 19 County Council by-elections in the
  configured official archive catalogue.
- 1,992 candidate rows and 343 division or ward rows.
- Complete 81 reviewed-row 2021-to-2026 geographic lookup: 24 approved direct
  relationships, 36 changed-boundary wards and 21 wards without sufficient
  weighted-crosswalk evidence for a direct historical value.
- 205 approved historical references: 81 for 2013→2017, 81 for 2017→2021,
  19 for by-elections and 24 for 2021→2026.
- Official, supplementary, derived and analysis layers remain separate. No
  official `NULL` is overwritten.

## Supervisor field coverage

The detailed field-by-field matrix is
[`supervisor_field_coverage_matrix.md`](supervisor_field_coverage_matrix.md).
The release-critical summary is:

| Required area | Current release position | Evidence boundary |
| --- | --- | --- |
| Election and area identifiers | 24/24 events; 343/343 areas | Configuration plus official event/result sources. |
| Candidate names, votes, outcomes and URLs | 1,992/1,992 | Every candidate, including all candidates in the 81 two-member 2026 wards. Published names are retained separately from deterministic display-standard names; neither field establishes identity continuity. |
| Published/standardised party and category | Published 1,991/1,992; analytical 1,992/1,992 | The officially blank 2013 party cell remains NULL in the original field and uses `No published party label` with an unaffiliated/independent analytical category. UKIP label variants share one reviewed standard name, but their published wording is retained and Reform UK remains separate. |
| Party history and new entrants | 40/40 standard parties | First observation is defined relative to the 2013 study start. Reform UK records UK Independence Party as historical context only, never as party continuity or a source of substituted votes. |
| 2021-to-2026 geographic lookup | 81/81 current wards | 24 approved direct, 36 changed-boundary/non-direct and 21 insufficient weighted-evidence rows. Every ward is visible; only approved direct rows may expose historical values. |
| Vote share | 1,986 official; 1,992 analysis-ready | Six Epsom West 2015 shares are governed calculations from the complete official candidate-vote table and never fill the official field. |
| Final position | 0 official; 1,992 separate derived competition ranks | Official formats do not publish rank. Eight tied rows retain tie flags; vote order never becomes an official field. |
| Seats | 315 official; 28 supplementary; 343 analysis-ready | Statutory supplementary evidence does not overwrite official `NULL`. |
| Winning outcome and margin | Official elected names for 343/343 areas; 343 labelled analysis margins | 262 single-seat runner-up gaps and 81 two-member final-seat cutoff gaps. Official margin remains `NULL`. |
| Electorate | 341/343 official | Staines South & Ashford West 2016 and Walton South & Oatlands 2023 remain source-unavailable. |
| Ballot papers issued | 256 official; 340 supported across permitted layers | Weybridge 2015, Walton South & Oatlands 2023 and Woking South 2025 remain unsupported. |
| Turnout | 257 official; 83 division supplementary; 340 supported | Weybridge 2015, Haslemere 2019 and Walton South & Oatlands 2023 remain unsupported. |
| Rejected ballots | 341 official; 1 governed derived; 342 supported | Weybridge 2015 remains unsupported. |
| Previous winning party | 205/343 approved area references | No predecessor is invented outside an approved legal, statutory or geographic relation. |
| Previous party vote share | 1,042/1,992 candidate rows | Candidate-level exact published-party label under an approved predecessor; never a reconstructed multi-candidate party total. |
| Change in vote share | 796/1,992 candidate rows | Post-election diagnostic only; excluded from every no-news predictor. |
| Candidate previously stood | 360 True; 1,274 False; 358 Unknown | All Unknown rows are the 2013 first-period boundary. No fuzzy identity matching. |
| Incumbent candidate | 116 Yes; 1,518 No; 358 Unknown | Complete chronological pre-election councillor roster; all Unknown rows are 2013. |
| Incumbent party | 171 Yes; 631 No; 1,190 Unknown | Only approved comparable historical areas; altered or two-member geography remains Unknown. |
| First observed party appearance | 1,060/1,992 | Exact published labels within approved lineages; this is not a claim about real-world party origin. |

## Residual official-source gaps

The release audit retains nine division-level unsupported values: two
electorate values, three issued-ballot counts, three turnout values and one
rejected-ballot count. The six missing official Epsom West vote-share cells form one page-level
gap but have complete, separately labelled analysis values.

These records have reviewed-source documentation in the final missing-field
index. They are publication or archive limits, not permission to infer values.
A future value may be added only with a new authoritative division-specific
source or a separately approved transparent calculation.

## No-news boundary

The current no-news JSON contains 343 division-level rows: 205 have an approved
historical predecessor and 138 do not. Previous turnout is available for all
205 eligible rows (120 official result-page values and 85 supplementary
official values). Runtime checks prohibit current result, rank, margin and
vote-share outcome fields.

The candidate-level modelling table this boundary once awaited is published:
the candidate-contest release (`outputs/no_news_candidate_contests/`, 1,992
rows) carries the 1,042 candidate-level exact-label previous-party shares and
is the final Stage 1 input contract. This does not reopen election extraction.

## Readiness decision

The **election extraction and governed analytical data are release-ready with
visible evidence boundaries**. Remaining official `NULL` values are retained
deliberately and all supervisor fields have either a value-bearing layer or an
explicit, documented non-identifiability boundary.

The **no-news modelling input is complete**: the division-level export and the
candidate-contest release together publish every governed lagged predictor the
Stage 1 baseline consumes. They remain two separate release decisions.
