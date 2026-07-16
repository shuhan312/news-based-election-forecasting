# 2013 Elmbridge issued-ballots recovery audit

## Scope

This is a read-only recovery audit for the nine 2013 Surrey County Council
divisions administered in the Elmbridge area:

- Cobham
- East Molesey and Esher
- Hersham
- Hinchley Wood, Claygate and Oxshott
- The Dittons
- Walton
- Walton South and Oatlands
- West Molesey
- Weybridge

The Surrey individual result pages preserve candidate results and electorate,
but do not publish `ballot_papers_issued`.  No value is added by this audit.

## Official sources reviewed

1. The [archived Elmbridge 2013 County Council election page](https://web.archive.org/web/20130530111102id_/http://www.elmbridge.gov.uk/council/elections/SCC2013info.htm)
   is an Elmbridge Borough Council page dated 2013.  It explicitly identifies
   the nine County divisions above and states that the results would be
   published after the count.
2. The [archived Elmbridge election-results index](https://web.archive.org/web/20131216211434id_/http://www.elmbridge.gov.uk/council/elections/results.htm)
   explicitly links to “Surrey County Council Results 2013” on the former
   official `elections.elmbridge.gov.uk` results service, at
   `Results/ElectionResults.aspx?e=60`.
3. The Internet Archive CDX index was queried for the exact former results URL
   and its `Results/` path.  It retains a generic 2013 results-service capture,
   but no capture of the query-specific 2013 election page or any division
   result table containing ballot-papers-issued values.
4. The Common Crawl 2013 summer index independently preserves the Elmbridge
   election-results index dated 23 May 2013.  Its original HTML confirms the
   same `e=60` official County-results link.  Common Crawl has no capture of
   the former `elections.elmbridge.gov.uk/Results/` host in its 2013 summer,
   2013 winter, or early-2014 indexes.
5. The former official results host was also checked directly.  It is no longer
   reachable, so it cannot be used as a current primary source.
6. The independent [Arquivo.pt](https://arquivo.pt) public web archive was
   queried for both the exact former `e=60` results URL and the Elmbridge
   results index URL.  It has zero captures for both paths.
7. Targeted indexed searches for the former host, 2013 Elmbridge County results
   and ballot-papers-issued wording returned no further official document.

## Result

The reviewed evidence confirms that Elmbridge operated an official 2013 County
Council results service, but it does **not** recover a published
division-level `ballot_papers_issued` value.  The source was unavailable in the
reviewed public archive; this is not evidence that the value was never
published.

All nine affected official Surrey fields remain `NULL`.  No secondary value,
derived value, or completeness change is created.  A future request to
Elmbridge Electoral Services or the relevant returning officer could still
recover the declaration or ballot-account evidence.
