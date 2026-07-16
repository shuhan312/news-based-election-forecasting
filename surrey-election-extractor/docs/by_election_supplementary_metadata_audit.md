# Surrey County Council By-election Supplementary Metadata Audit

## Scope and rule

Reviewed on 16 July 2026: all fields still missing from the 15-event
Surrey County Council by-election register. The search order was: the relevant
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

## Fields that remain unknown in this audited source scope

| Event | Fields remaining NULL | Official/authoritative material checked | Decision |
| --- | --- | --- | --- |
| Weybridge, 7 May 2015 | ballot papers issued; rejected ballots; turnout | [Official Surrey detail page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=169&RPID=0); [Surrey News result announcement](https://news.surreycc.gov.uk/tag/county-council-elections/) | The canonical detail page and reviewed Surrey News source publish candidates, total votes and electorate but not the three fields. No secondary value is added. |
| Epsom West, 19 November 2015 | total votes; candidate vote shares | [Epsom & Ewell official declaration](https://www.epsom-ewell.gov.uk/sites/default/files/documents/council/elections-and-voting/SCCDeclarationofResults19Nov2015.pdf); [Surrey News result announcement](https://news.surreycc.gov.uk/2015/11/20/karan-persand-wins-county-council-by-election/) | Both sources publish candidate votes but neither publishes a total or vote shares. The project must not calculate either field, so no supplementary value is added. |
| Staines South & Ashford West, 5 May 2016 | electorate; ballot papers issued | [Official Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=171&RPID=0); [Spelthorne Borough Council declaration](https://www.spelthorne.gov.uk/page/306/staines-south-and-ashford-west-election-5-may-2016) | The reviewed official page publishes seats, total votes and rejected ballots; the declaration separately supplies turnout but not electorate or issued ballot papers. No further value is added. |
| Haslemere, 2 May 2019 | ballot papers issued; turnout | [Official Surrey division result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=257&RPID=0); [Surrey News announcement](https://news.surreycc.gov.uk/2019/05/03/nikki-barton-elected-in-haslemere-by-election/); [LGA First Political report](https://www.lgafirst.co.uk/wp-content/uploads/2019/06/First-637-July-2019.pdf) | The Council sources do not publish issued papers or turnout. The LGA report states 42.9% turnout, but that conflicts with the official total votes (4,087), rejected ballots (58) and electorate (9,536), so it is rejected rather than integrated. |
| Addlestone, 21 August 2025 | ballot papers issued | [Official Surrey result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=346&RPID=0); [Runnymede Borough Council announcement](https://www.runnymede.gov.uk/news/article/270/by-election-results-in-addlestone); [WhoCanIVoteFor result page](https://whocanivotefor.co.uk/elections/local.surrey.addlestone.by.2025-08-21/addlestone/) | The official announcement supplies turnout only, not issued ballot papers. WhoCanIVoteFor lists 2,726 issued papers, but this equals the official candidate-vote total while the official page also records 8 rejected ballots; it is internally inconsistent with the official evidence and is rejected. |

## Conclusion

The audit corrects one missed **official** candidate-table value and approves
two separately sourced turnout values. All other listed fields remain unknown
within the documented reviewed sources. This is an evidence boundary, not a
claim that a value can never be found in a future archive search. Any future
addition must be a new supplementary record with division-specific evidence;
it must not overwrite the original official `NULL`.

## Archive-search boundary

The corresponding returning-authority domains (Elmbridge, Waverley, Spelthorne
and Runnymede) and public indexed results were searched. A public Internet
Archive CDX query for 2015 Elmbridge pages timed out without a response, so it
cannot support either a positive or negative conclusion. A future request to
the relevant returning officer remains the only route to a stronger conclusion
for values that were not published online.
