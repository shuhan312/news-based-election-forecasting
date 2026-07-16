# 2017 Reigate rejected-ballot provenance audit

## Scope

This is a read-only source audit for the missing `rejected_ballots` field in
the Surrey County Council **Reigate** division election held on 4 May 2017.
It does not alter official extraction data, validation status or the
supplementary metadata register.

## Verified official result evidence

| Source | What it publishes for Reigate | Rejected-ballot value |
| --- | --- | --- |
| [Surrey County Council result page](https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=230&RPID=454155221&XXR=0) | Candidate results, total votes (4,109), electorate (10,443), ballot papers issued (4,109), and turnout (39%). | Not published. |
| [Archived Reigate & Banstead 2017 County Council results](https://web.archive.org/web/20170509022147id_/http://www.reigate-banstead.gov.uk:80/info/20318/voting_and_elections/299/county_council_elections) | Candidate declaration-style table and turnout (39.3%). | Not published. |

The two official pages corroborate the candidate vote totals and election
outcome. They use different displayed turnout precision, so the existing
Surrey result-page value remains the official extracted value. The borough
page is not used to replace it.

## Additional source checks

| Source or search scope | Result | Decision |
| --- | --- | --- |
| [WhoCanIVoteFor 2017 Reigate result](https://whocanivotefor.co.uk/elections/local.surrey.reigate.2017-05-04/reigate/) | Repeats candidates, issued papers and turnout, but does not state rejected ballots. | Not sufficient evidence. |
| Internet Archive CDX index for Reigate & Banstead 2017 election pages and downloads | Recovered the official borough result page, notices and nomination/poll documents. It did not recover a 2017 county-election declaration of result or ballot-account document containing a rejected-ballot total. | No value available for integration from the reviewed archive. |

## Decision

`rejected_ballots` remains `NULL` for Reigate 2017. In particular, the fact
that the published total votes and issued ballot papers are both 4,109 is not
evidence that zero ballot papers were **published** as rejected. It must not
be written into the official field.

This audit establishes the checked source scope, not a claim that no record
can exist anywhere. The only further authoritative route would be a result
declaration or ballot-account record supplied by the relevant Returning
Officer. Any future value must be stored as separate, source-backed
supplementary metadata and must not overwrite the official missing field.

The project now also keeps the arithmetic result in a separate **derived
metadata** layer: `4,109 - 4,109 = 0`. It is explicitly labelled calculated,
keeps this official source URL and does not change the official
`rejected_ballots` value, source provenance or completeness status.
