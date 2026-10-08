# Outlet-first pilot: findings

**2026-10-08.** Design, sample and criteria were committed before any fetch
(79f8c88). The expansion rule was committed before any result was read
(333e5e5). Outputs: `pilot_report.json`, plus per-article caches in
`data/v2_pilot/` (gitignored). Classification cost: 202,370 input and 25,763
output tokens on claude-sonnet-5 via the Batches API, about US$0.33.

## Headline

**K1 is undefined (0/0), so the pre-registered comparison is inconclusive.
The pilot nevertheless answers the question behind it:** in a 90–31 day
pre-election window, local outlets' relevant coverage is council-service
news that almost never names a party. Of 13 articles classified relevant
across both counties, **one** names a main party. Council-level,
**party-specific** local content features are too sparse to support V2's
primary test, in Kent and Surrey alike.

## Funnel

| outlet | URLs listed | in window (of 100) | prefilter pass | classified ok | relevant |
|---|---:|---:|---:|---:|---:|
| getsurrey.co.uk/news/ | 38,552 | 3 | 2 | 1 | 1 |
| BBC Surrey | 231 | 5 | 0 | 0 | 0 |
| surreycomet.co.uk/news/ | 6,811 | 68 | 18 | 14 | 0 |
| kentlive.news/news/ | 3,964 | 45 | 8 | 8 | 2 |
| BBC Kent | 619 | 11 | 3 | 3 | 2 |
| KentOnline (23 sections) | 7,745 | 27 | 10 | 9 | 8 |

P3, the real prefilter removal rate, is 74% (Surrey) and 75% (Kent).

## Why K1 is undefined: the Surrey calibration arm failed

- **getsurrey.co.uk:** only 3 of 100 sampled URLs were published in the
  window. The 38,552 listed URLs are mostly old articles re-crawled under
  SurreyLive's retired domain. One relevant article is far too few to
  measure from.
- **Surrey Comet's `/news/` section is mostly national wire copy** (PA
  stories: lockdown briefings, Scottish Labour, smart motorways, "What the
  papers say"). The classifier correctly excluded all 14 classified
  articles. These stories name parties, which is why they passed the
  prefilter, but they are not Surrey news.

So the Surrey side measured re-crawl noise and syndication, not Surrey's
local political coverage. That is a sampling-frame failure, not a
classifier failure.

## What the Kent side shows

KentOnline is a genuine local source: 8 of 9 classified articles are
relevant, and all are council or civic stories (planning appeals, bin
collections, an access-road charge, virtual council meetings, the Brexit
lorry ban). KentLive and BBC Kent add 4 more. **None names a main party.**
The prefilter passed them on civic words ("council", "cllr", "MP").

## Why a larger sample would not change this

The A1 expansion band does not cover an undefined K1, and expanding would not
help in any case. The bottleneck is not sample size but what local news is
about: council services, reported without party labels. Tripling the
sample would yield roughly 3 party-naming relevant articles instead of 1.
This matches V1, where the whole local arm contributed only 108 articles to
party features across all Surrey elections.

## Consequences for V2

1. **Do not build V2's primary test on council-level, party-named local
   coverage.** The data will not be there at any feasible scale.
2. **Local coverage can still reach parties through council control.**
   Council-service stories (bins, planning, roads, budgets) are implicitly
   about the controlling party's record. Attributing them to the party in
   control, as an "incumbent performance" signal, turns the abundant
   unlabelled coverage into a party-level feature. This fits the one content
   lead from `power_v1`: the incumbent-judgement frame leaned positive out of
   sample.
3. **National coverage varies by date, not council.** More election dates
   (for example, English council by-elections across many weeks) are the
   lever for national content, not more councils on one polling day.
4. **Engineering lessons:** Wayback listings are slow and noisy, so prefer
   outlet sitemaps. Check each outlet's in-window and syndication share
   before relying on it. Parse errors were 6/41 (15%, against ~1% in V1), all
   from the verbatim-evidence check, likely text-encoding differences in
   freshly parsed pages (e.g. mojibake in curly quotes). Normalise text
   before classification.

## Caveats

- 100 URLs per outlet; all counts are small.
- "Relevant" comes from the frozen classifier without a human reference on
  these outlets.
- Party mention is a keyword proxy for "would feed a party feature".
