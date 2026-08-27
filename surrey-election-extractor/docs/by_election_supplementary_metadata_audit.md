# Surrey County Council By-election Supplementary Metadata Audit

## Scope and rule

Reviewed on 16 July 2026: all fields still missing from the initial
15-event tranche of the Surrey County Council by-election register as it
stood on that date. The current release contains 19 by-elections; the later
additions are governed by their committed event and source evidence rather
than by this audit. The search order was: the relevant
returning authority and Surrey County Council publications, official archive
pages and declarations, then public indexed results. This document records
the reviewed evidence scope; it does **not** claim that no unpublished document
exists anywhere.

An official field remains `NULL` unless the official result page or declaration
publishes it. A separately published value may be recorded only as
Supplementary Metadata with its own URL, evidence text and geographic scope.
It cannot replace the official field or change completeness.

## Corrections to official extraction evidence

| Event | Field | Decision | Evidence |
| --- | --- | --- | --- |
| Staines South & Ashford West, 5 May 2016 | Clarke Matthew David: party and votes | Corrected in the official result register: `Trade Unionist and Socialist Coalition`, `33`. This is not supplementary data. | The [official Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=171&RPID=0) publishes both values in its candidate table. |

## Verified supplementary metadata

| Event | Official field still NULL | Separate metadata field | Value | Evidence and decision |
| --- | --- | --- | --- | --- |
| Addlestone, 21 August 2025 | turnout | `secondary_division_turnout` | 24.0% | The [Runnymede Borough Council result announcement](https://www.runnymede.gov.uk/news/article/270/by-election-results-in-addlestone) explicitly identifies the one-seat Surrey County Council Addlestone Division by-election and states that its turnout was 24%. It is stored separately with high confidence. |
| Staines South & Ashford West, 5 May 2016 | turnout | `secondary_division_turnout` | 31.3% | The [Spelthorne Borough Council declaration](https://www.spelthorne.gov.uk/page/306/staines-south-and-ashford-west-election-5-may-2016) names the same County Council contest and states that the votes represented 31.3% of registered electors. It is stored separately with high confidence. |

## Governed derived issued-ballot values

These records are not supplementary sources and they do not fill the official
`ballot_papers_issued` field.  Each result comes only from `total_votes +
rejected_ballots` published on the **same** official one-seat result page.  The
one-seat condition matters: it ensures that the published total-vote count is
the valid ballot count for this calculation.

| Event | Derived metadata field | Calculation | Official result page |
| --- | --- | --- | --- |
| Staines South & Ashford West, 5 May 2016 | `derived_ballot_papers_issued` | `3,383 + 21 = 3,404` | [Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=171&RPID=0) |
| Haslemere, 2 May 2019 | `derived_ballot_papers_issued` | `4,087 + 58 = 4,145` | [Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=257&RPID=0) |
| Addlestone, 21 August 2025 | `derived_ballot_papers_issued` | `2,726 + 8 = 2,734` | [Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=346) |
| Epsom West, 19 November 2015 | `derived_total_votes` | `2,602 - 7 = 2,595` | [Epsom & Ewell signed declaration](https://www.epsom-ewell.gov.uk/sites/default/files/documents/council/elections-and-voting/SCCDeclarationofResults19Nov2015.pdf) |

## Fields that remain unknown in this audited source scope

| Event | Fields remaining NULL | Official/authoritative material checked | Decision |
| --- | --- | --- | --- |
| Weybridge, 7 May 2015 | ballot papers issued; rejected ballots; turnout | [Official Surrey detail page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=169&RPID=0); [Surrey News result announcement](https://news.surreycc.gov.uk/tag/county-council-elections/) | The canonical detail page and reviewed Surrey News source publish candidates, total votes and electorate but not the three fields. No secondary value is added. |
| Epsom West, 19 November 2015 | candidate vote shares | [Epsom & Ewell official declaration](https://www.epsom-ewell.gov.uk/sites/default/files/documents/council/elections-and-voting/SCCDeclarationofResults19Nov2015.pdf); [Surrey News result announcement](https://news.surreycc.gov.uk/2015/11/20/karan-persand-wins-county-council-by-election/) | The one-seat official declaration supports a separate derived total-vote value from issued minus rejected ballots. Neither source publishes candidate vote shares, and this project does not calculate or substitute them. |
| Staines South & Ashford West, 5 May 2016 | electorate | [Official Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=171&RPID=0); [Spelthorne Borough Council declaration](https://www.spelthorne.gov.uk/page/306/staines-south-and-ashford-west-election-5-may-2016) | The official page provides the inputs for a separate derived issued-ballot value, while the declaration separately supplies turnout. Neither source publishes electorate. |
| Haslemere, 2 May 2019 | turnout | [Official Surrey division result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=257&RPID=0); [Surrey News announcement](https://news.surreycc.gov.uk/2019/05/03/nikki-barton-elected-in-haslemere-by-election/); [LGA First Political report](https://www.lgafirst.co.uk/wp-content/uploads/2019/06/First-637-July-2019.pdf) | The official page provides the inputs for a separate derived issued-ballot value. The Council sources do not publish turnout. The LGA report states 42.9% turnout, but that conflicts with the official total votes (4,087), rejected ballots (58) and electorate (9,536), so it is rejected rather than integrated. |
| Addlestone, 21 August 2025 | — | [Official Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=346&RPID=0); [Runnymede Borough Council announcement](https://www.runnymede.gov.uk/news/article/270/by-election-results-in-addlestone) | No remaining voting-summary field is unresolved after the separately sourced turnout and the governed derived issued-ballot value. |

## Conclusion

The audit corrects one missed **official** candidate-table value, approves two
separately sourced turnout values, and now records three governed derived
issued-ballot values. The remaining listed fields are unknown within the
documented reviewed sources. This is an evidence boundary, not a claim that a
value can never be found in a future archive search. Any future addition must
be a new supplementary or derived record with division-specific evidence; it
must not overwrite the original official `NULL`.

## Archive-search boundary

The corresponding returning-authority domains (Elmbridge, Waverley, Spelthorne
and Runnymede) and public indexed results were searched. A public Internet
Archive CDX query for 2015 Elmbridge pages timed out without a response, so it
cannot support either a positive or negative conclusion. A future request to
the relevant returning officer remains the only route to a stronger conclusion
for values that were not published online.
