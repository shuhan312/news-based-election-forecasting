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
| Candidate names, votes, outcomes and URLs | 1,971/1,992 | Every candidate, including all candidates in the 81 two-member 2026 wards. Published names are retained separately from deterministic display-standard names; neither field establishes identity continuity. |
| Published/standardised party and category | Published 1,970/1,992; analytical 1,971/1,992 | The officially blank 2013 party cell remains NULL in the original field and uses `No published party label` with an unaffiliated/independent analytical category. UKIP label variants share one reviewed standard name, but their published wording is retained and Reform UK remains separate. |
| Party history and new entrants | 40/40 standard parties | First observation is defined relative to the 2013 study start. Reform UK records UK Independence Party as historical context only, never as party continuity or a source of substituted votes. |
| 2021-to-2026 geographic lookup | 81/81 current wards | 24 approved direct, 36 changed-boundary/non-direct and 21 insufficient weighted-evidence rows. Every ward is visible; only approved direct rows may expose historical values. |
| Vote share | 1,965 official; 1,971 analysis-ready | Six Epsom West 2015 shares are governed calculations from the complete official candidate-vote table and never fill the official field. |
| Final position | 0 official; 1,971 separate derived competition ranks | Official formats do not publish rank. Eight tied rows retain tie flags; vote order never becomes an official field. |
| Seats | 311 official; 28 supplementary; 339 analysis-ready | Statutory supplementary evidence does not overwrite official `NULL`. |
| Winning outcome and margin | Official elected names for 339/339 areas; 339 labelled analysis margins | 258 single-seat runner-up gaps and 81 two-member final-seat cutoff gaps. Official margin remains `NULL`. |
| Electorate | 338/339 official | Staines South & Ashford West 2016 remains source-unavailable. |
| Ballot papers issued | 254 official; 338 supported across permitted layers | Weybridge 2015 remains unsupported. |
| Turnout | 254 official; 83 division supplementary; 337 supported | Weybridge 2015 and Haslemere 2019 remain unsupported. |
| Rejected ballots | 337 official; 1 governed derived; 338 supported | Weybridge 2015 remains unsupported. |
| Previous winning party | 201/339 approved area references | No predecessor is invented outside an approved legal, statutory or geographic relation. |
| Previous party vote share | 1,042/1,992 candidate rows | Candidate-level exact published-party label under an approved predecessor; never a reconstructed multi-candidate party total. |
| Change in vote share | 796/1,992 candidate rows | Post-election diagnostic only; excluded from every no-news predictor. |
| Candidate previously stood | 360 True; 1,274 False; 358 Unknown | All Unknown rows are the 2013 first-period boundary. No fuzzy identity matching. |
| Incumbent candidate | 116 Yes; 1,518 No; 358 Unknown | Complete chronological pre-election councillor roster; all Unknown rows are 2013. |
| Incumbent party | 171 Yes; 631 No; 1,190 Unknown | Only approved comparable historical areas; altered or two-member geography remains Unknown. |
| First observed party appearance | 1,060/1,992 | Exact published labels within approved lineages; this is not a claim about real-world party origin. |

## Residual official-source gaps

The release audit retains five division-level unsupported values: one
electorate, one issued-ballot count, two turnout values and one rejected-ballot
count. The six missing official Epsom West vote-share cells form one page-level
gap but have complete, separately labelled analysis values.

These records have reviewed-source documentation in the final missing-field
index. They are publication or archive limits, not permission to infer values.
A future value may be added only with a new authoritative division-specific
source or a separately approved transparent calculation.

## No-news boundary

The current no-news JSON contains 339 division-level rows: 201 have an approved
historical predecessor and 138 do not. Previous turnout is available for all
201 eligible rows (116 official result-page values and 85 supplementary
official values). Runtime checks prohibit current result, rank, margin and
vote-share outcome fields.

This division-level table is reproducible and leakage-safe, but it is **not yet
the complete party/candidate modelling table** required to predict party vote
shares: it does not publish the 1,021 candidate-level exact-label previous-party
shares. That downstream publication step must be completed before claiming the
whole no-news baseline is model-ready. This does not reopen election extraction.

## Readiness decision

The **election extraction and governed analytical data are release-ready with
visible evidence boundaries**. Remaining official `NULL` values are retained
deliberately and all supervisor fields have either a value-bearing layer or an
explicit, documented non-identifiability boundary.

The broader **no-news modelling input is not yet fully complete** because its
current division-level export does not include the candidate/party-level lagged
share table. Treat these as two separate release decisions.
