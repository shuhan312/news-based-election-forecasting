# Faults found in the news collection, and what they cost

**Recorded 29 July 2026.** Extending collection to the by-elections meant
running parts of the pipeline that had not been re-run since they were
written. Six faults surfaced, all of the same shape: the log said a search had
happened, and it had not. Each is recorded here with the measurement that
found it, because "we searched and found nothing" and "we never searched" are
the same row in a log and completely different facts about the world.

Two of the entries are corrections to conclusions recorded earlier in the same
day. They are kept rather than overwritten.

---

## 1. The declared search route had never worked

`query_inventory.csv` named `google_cse` as the retrieval route for all 1,112
ward-tier queries. That route has been attempted **twice in the project's
history and returned HTTP 403 both times.**

What actually executed those queries was Serper (1,422 searches) and SerpApi
(313). The inventory named Serper until it was switched to Google CSE on
26 July; nobody regenerated it afterwards, so the file described a route the
runner would fail on at the first request.

The route is now declared as `serper`, which is the one that works and the one
the log says ran.

## 2. Quoted queries fail on Serper, and one whole family was quoted

Every one of the 91 searches that ever returned HTTP 400 contained a double
quote. Not one of the 1,331 that returned 200 did. Probing the endpoint
confirms the rule directly:

```
Addlestone AND Reform UK          -> 200, 10 results
"Addlestone" AND Reform UK        -> 400 "Query pattern not allowed for free accounts"
"Surrey County Council" AND Addlestone -> 400
```

The supervisor's own search examples are quoted, so the quoting was faithful
to the brief rather than careless. But it meant the family
`"Surrey County Council" AND <division>` — one query per division per election,
52 of them — returned nothing for the entire collection while appearing in
the inventory as searched.

Quotes are now stripped for the Serper route. An unquoted query recalls more
and is less precise; a quoted one is not a search at all.

### Correction: those queries were not zero-yield

This was first recorded as "100% failure, zero output". That was wrong, and
the error came from checking only the Serper route. Across their full history
the 52 quoted queries ran 119 times: **91 returned 400, 13 hit a SerpApi quota
limit, and 15 returned 200 — writing 41 articles that are still on disk.**

SerpApi accepts phrase quoting; Serper does not. So the same query text
behaved differently depending on which route was live, and dropping the
quoted query ids from the inventory would have orphaned 41 real articles.
Both forms are now emitted — the unquoted one at stage M on Serper, the
quoted original at stage M2 on SerpApi — so nothing is orphaned and no Serper
credit is spent on a pattern that route rejects.

**Methodological consequence worth carrying forward:** articles collected
before the route switch were found by quoted, higher-precision queries;
articles collected after were found by unquoted, wider ones. Extraction keeps
`search_query_id` on every record, so whether a result depends on the
retrieval route can be tested later. It has not been tested yet.

## 3. Searches that never reached the engine were checkpointed as done

The runner ended every query with an unconditional `done.add(query_id)`. A
transport failure — connection reset, DNS failure, timeout — returns no hits
and no HTTP status, and was recorded as a completed search with zero results.

Measured on the first by-election pass: **78 of 166 stage-F searches failed
this way**, and four by-elections returned nothing at all:
Nork & Tattenhams, Woking South, Sunbury Common & Ashford Common, and
Warlingham. Every one would have stayed empty on every future run, and the
log would have kept saying "0 results" where the truth was "never asked".

Fixed three ways: the runner now checkpoints only searches that reached the
engine; the 78 affected ids were reopened; and Serper calls are spaced two
seconds apart, since a 47 per cent reset rate against a key that succeeded on
the other 88 searches is a rate-limit signature rather than a network fault.

A status of 200 with zero results is a real answer and is still checkpointed.
Only "the engine was never reached" is left open for retry.

## 4. Ward-level archive search ran against one publisher out of seven

`ward_cdx` — the query family that searches a publisher's Wayback archive for
URLs containing a division name — was emitted for `surreylive` only.

The measured productivity of the CDX route across the four principal
elections:

| publisher | records written |
| --- | ---: |
| surreylive | 3,187 |
| bbc_surrey | 1,684 |
| surrey_comet | 804 |
| farnham_herald | 785 |
| woking_news_mail | 467 |
| guildford_dragon | 52 |
| epsom_ewell_times | 2 |

3,794 records from six publishers that were never searched at ward level. The
gap became visible when the search-engine tier retrieved 700 articles for the
by-elections of which **10 came from a Surrey local publisher** — the rest
were national outlets and social media, which cannot be located to a division.

`ward_cdx` now runs across all seven. The inventory went from 1,992 to 2,470
queries, and stage C (the 17 sampled divisions across four elections) from 52
to 364.

### What the expansion actually yielded

Running the expanded 2021 ward search first: **91 queries produced 21 new
records.** That is a real answer and not an encouraging one — the local
archive for 2021 is genuinely thin, and the previous single-publisher search
was not the binding constraint there. It may still be for the by-elections,
where archives are complete; that is still running.

## 5. Reform UK has no article-level record before 2026

Of the 207 article-level observations in the corpus, **11 mention Reform UK
and all 11 are 2026.** The 2021 breakdown is Conservative 13, Labour 12,
Liberal Democrats 7, Guildford Greenbelt Group 5, Residents for Guildford and
Villages 5, Green 1 — no Reform at all.

This is not an extraction failure. Reform UK was renamed from the Brexit Party
in January 2021, contested 6 of 81 divisions, and polled 3 per cent where it
stood; local news barely covered it, and it did not exist in 2013 or 2017.

The consequence is that the by-elections of 2022–2025 are not "more data" but
**the only period in which Reform news plausibly exists at all**, which is why
collection was extended there first.

## 6. Election-wide news is not one value per election

Recorded here because it was stated wrongly twice in one day.

The first claim was that election-wide news features are collinear with
election identity and therefore useless. The measurement says otherwise: the
election-wide rows are keyed by **election × party × window** — 168 rows
across 4 elections, 7 parties and 12 windows.

That matches the brief, which says national articles are "stored once and
linked to the relevant party, election and time period", and sets the
hypothesis that national coverage identifies a party's momentum while local
coverage identifies which wards convert it. National news is a first-class
arm of the design, not a defect.

The original collinearity worry was only ever true of the *current* data,
where two elections share a baseline and news. It does not describe the design.

**But it does not rescue Reform either.** Reform's 13 election-wide rows are
all 2026, which is the holdout. In the training period the count is zero at
both tiers.

---

## The deliverable was also stale

Not a collection fault, but found in the same session and the same shape.

The committed master workbook was generated on 21 July and holds **20
elections and 1,971 candidate rows**. Four by-elections have been recovered
from the archive since, and the current contract holds **24 and 1,992**. The
workbook therefore disagreed with every figure in the model bundle, and the
four missing contests are exactly the ones where Reform polled 19–34 per cent
— so the stale file understated the party the project is about.

The payload was regenerated before the combined workbook was built. Anything
quoting the 21 July workbook should be rechecked.

---

## What is now true of the collection

| | |
| --- | --- |
| queries in the inventory | 2,470 |
| by-election queries added | 1,119 |
| routes declared correctly | yes, verified against the log |
| queries containing double quotes | 0 on the Serper route, 52 retained on SerpApi |
| searches checkpointed without reaching the engine | 0 |
| ward-level archive publishers | 7 |

---

## Related records

- [`news_research_protocol.md`](news_research_protocol.md) — the collection
  plan and its deviations log
- `news_collection/search_log.csv` — the permanent record; every failure above
  is visible in it
