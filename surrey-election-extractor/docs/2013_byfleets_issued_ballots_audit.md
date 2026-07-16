# 2013 The Byfleets ballot-papers-issued provenance audit

## Purpose

This is a read-only follow-up to the 2013 division supplementary-evidence
audit. It examines whether `ballot_papers_issued = 2,945` can safely be added
as a **separate** division-level supplementary value for The Byfleets. It does
not alter the Surrey official extracted fields.

## Official evidence reviewed

| Source | What it publishes for The Byfleets | Result |
| --- | --- | --- |
| [Surrey County Council individual result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=152&RPID=454305731&XXR=0) | Candidate results and `electorate = 10,019`; it does not publish ballot papers issued. | This is the official extraction source. |
| [Woking Borough Council signed declaration](https://www.woking.gov.uk/sites/default/files/documents/council-and-democracy/elections/ElectionResults/resultsscc.pdf) | The same named division, candidates and winner; `electorate = 10,016`, `ballot papers issued = 2,945`, `turnout = 29.40%`. The PDF is dated 3 May 2013 and published by the Deputy Returning Officer. | Strong named official evidence for 2,945, but its electorate conflicts with the Surrey page. |
| [Surrey County Council 2013 results announcement](https://news.surreycc.gov.uk/2013/05/03/election-results-special/) | The same candidate results and `turnout = 29%` for The Byfleets. | Independently corroborates the rounded turnout only; it does not publish electorate or ballot papers issued. |

## Checks performed

- The two official result sources name **The Byfleets** and report the same five
  candidates, candidate votes and elected candidate.
- `2,945 / 10,016 = 29.4029...%`, which is consistent with Woking's published
  `29.40%` and the Surrey announcement's rounded `29%`.
- The Surrey individual result page records `electorate = 10,019`, not
  `10,016`. The three-voter difference is not explained by any reviewed
  official source.
- Targeted searches of Surrey County Council, Woking Borough Council, the
  Electoral Commission and UK public-web archive indexes recovered no
  additional authoritative 2013 declaration that both publishes `2,945` and
  reconciles the electorate to `10,019`.
- On 16 July 2026, an exact Internet Archive CDX query for Woking's declaration
  PDF in 2013–2014 returned no captures. A narrower Woking election-URL CDX
  query also returned no captures. This records archive coverage, not a claim
  that no historical document ever existed.

## Decision

`secondary_division_ballot_papers_issued = 2,945` is accepted as a separate
supplementary value for The Byfleets. This is supported by the named official
Woking declaration, the exact election date and division name, and the exact
five-candidate vote list shared with the Surrey official result page.

The different electorate is not silently resolved. The record is explicitly
marked `accepted_with_source_discrepancy`, retains both `10,016` and `10,019`
in its evidence note, and never replaces Surrey's official electorate.

The official fields remain unchanged:

| Field | Stored value |
| --- | --- |
| `official_electorate` | `10,019` |
| `official_ballot_papers_issued` | `NULL` |
| `official_turnout` | `NULL` |

The existing 2013 turnout supplementary record remains valid: it is based on
the Surrey Council announcement's explicitly named, rounded `29%`, not on a
calculation from the conflicting electorates.

## What would change this decision

A further official source or written clarification from the Returning Officer
would be needed only to explain or reconcile the `10,016`/`10,019` electorate
discrepancy. It would not change the separate storage of the already published
issued-ballot value.
