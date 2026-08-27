# Scope of the news layer: which elections it covers, and why

> **Dated snapshot (30 July 2026).** The execution counts below reflect
> that date. The current frozen plan and log are
> `news_collection/query_inventory.csv` (2,470 planned queries) and
> `news_collection/search_log.csv`; planned-but-unexecuted queries are
> recorded as scope limitations by the repository-root leakage audit,
> never as zero-result searches.

Decided 2026-07-30, before the corpus was frozen and before any
full-corpus extraction was submitted. This document is what the report
cites for why the news analysis covers the elections it does.

## What prompted the decision

News collection had reached 1,681 of 2,470 planned queries when the
scheduler stalled: the round running at 01:15 was still alive at 03:17
having written two search-log rows in its first twenty-two minutes and
nothing for the hour and forty minutes after. Previous rounds completed
in eight to eighty minutes, so this was a hang, most likely a request
without a timeout - the wrapper has no sleep between rounds and no
per-request deadline. Both processes were stopped. The append-only log
and record store were unaffected: 2,684 log rows and 18,903 article
records before and after.

That left 789 queries outstanding. At the rate the last hour had
actually achieved - two queries - finishing them would have taken weeks,
which the project's remaining time does not allow. So the question became
which of the 789 the research question actually needs.

## Coverage as it stands

**The four principal elections were already at 95-98%**, and the 53
queries outstanding across them (52 at stage M, 1 at stage B) were run
directly. They are the elections the research question is about.

By-election coverage is not one number. It falls into three bands:

| Band | Elections | Coverage |
|---|---|---|
| Complete | Addlestone 2025-08-21, Camberley West 2025-10-16 | 100% |
| Partial | Caterham Valley 2025-10-16 | 54% |
| Partial | Nork & Tattenhams, Warlingham 2026, Guildford South East, Hinchley Wood, Woking South, Sunbury Common | 38-40% |
| Partial | Haslemere 2026-07-07 | 36% |
| Barely started | the nine 2015-2023 by-elections | 11-12% |

Overall by-election coverage is 379 of 1,119 queries, or 33%.

## The decision

**The news layer's primary analysis covers the four principal elections
(2013, 2017, 2021, 2026), where search coverage is complete.**

**By-elections are not excluded wholesale.** A blanket exclusion would be
coarser than the evidence supports - two of them are fully searched. The
rule instead is:

* every by-election carries its search-completeness figure as a feature
  alongside its news features, and
* a by-election may enter a news specification only where that figure is
  recorded and reported with the result.

This follows the project's existing archive-completeness discipline
rather than inventing a new one: `article_level_feature_dictionary.md`
already provides for archive-coverage indicators, and the protocol's
standing rule is that an incomplete archive must never be read as
neutral news. A by-election searched at 11% would contribute mostly
zero-valued news features, and those zeros mean "not searched", not "no
coverage existed". Admitting them unlabelled would be exactly the
inference the protocol forbids.

## Why the cost of this is low

The by-elections were already the thinnest part of the design, on grounds
recorded before tonight:

* Reform UK has single-digit observations across all by-elections
  combined, so they contribute almost nothing to the study party.
* `meeting_notes_2026-07-28.md` section 4 already proposes downgrading
  ward-level analysis to borough or county level, on the separate finding
  that only 13 of 81-91 divisions per election were searched.
* The residual feasibility diagnosis found only two elections with both a
  baseline prediction and division-level news, and both are principal
  elections.

So the analysis this scoping rules out is analysis the data could not
support in any case. What it rules out is the *pretence* of having
analysed it.

## What is being given up, stated plainly

Nine by-elections from 2015 to 2023 will have no usable news features.
Seven more will have partial coverage, usable only with their
completeness figure attached. The 741 unrun by-election queries remain in
`query_inventory.csv` as an open item; they are not deleted, and the
collection code can complete them if time allows later.

This also means the news layer cannot speak to whether by-elections
behave differently from principal elections under news pressure - a
question the supervisor's brief raises under robustness testing
("by-elections are analysed separately"). That robustness check is
therefore unavailable for the news layer, though it remains available
for the no-news baseline, which has complete election data for all 24
events.

## To tell the supervisor

Not a request for approval - reported under the standing
explore-first-report-after arrangement, since it touches none of the four
hard constraints (leakage, Reform/UKIP separation, the 2026 holdout, and
explicability) and is a scoping judgement of the kind delegated on
2026-07-29. The report should state: news search coverage is complete for
the four principal elections and 33% overall for by-elections, with nine
of them below 12%; the news analysis is therefore scoped to the principal
elections, with by-elections admitted only where their completeness
figure is recorded and reported.
