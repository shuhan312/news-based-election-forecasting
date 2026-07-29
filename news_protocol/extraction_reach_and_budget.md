# How many pending articles can reach a feature, and what that costs

Measured 29 July 2026 by `news_collection.measure_window_reach`, from dates
already on disk. Output: `news_collection/window_reach_assessment.json`.
Nothing was submitted to any API and nothing was spent.

The question this answers: extraction costs money and the pending corpus is
3,584 articles, so before committing a budget it is worth knowing how many of
those articles could affect the model **at all**, independently of what they
turn out to say.

> ## Resolved, same day
>
> This was measured while the window scheme was still open, and the scheme has
> since been settled: the six-window 180-day scheme is the one to use. That
> makes **every one of the 3,584 pending articles in-window** and the cost
> **$228.93**, not the $23.38 the 30-day sections below arrive at.
>
> The measurement is kept in full rather than rewritten, because the
> distribution it produced is what shows the two schemes are not a labelling
> difference: under 30-day windows nine tenths of the corpus is unreachable,
> and under the six-window scheme none of it is. Read sections 1 to 3 as the
> evidence, and section 5 for what actually follows.

---

## 1. The headline: 366 of 3,584

Under the principal windows currently in the feature table — the final day,
days 2–7, and days 8–30 — **366 pending articles land inside a window, 10.2% of
the corpus.**

| Where the 3,584 pending articles sit | Count |
|---|---:|
| Before the earliest window (31+ days out) | 3,218 |
| Days 8–30 | 255 |
| Days 2–7 | 87 |
| Final complete day | 24 |
| **Inside a principal window** | **366** |

The extracted pilot suggested this: 9 of its 67 articles were in-window, 13.4%.
The pending corpus comes in at 10.2%, so the pilot ratio held to within a few
points despite not having been drawn to be representative.

**No article is lost to dating or to post-polling exclusion.** All 3,584 carry
a usable effective date and none is dated on or after polling day — eligibility
screening removed those earlier, which is why the 5,026 `no_date_evidence`
articles in the date layer are all in the excluded set rather than the pending
one. The only thing standing between a pending article and a feature is how far
from polling day it was published.

---

## 2. The two breakdowns that matter

### By election — the validation split is the best covered

| Election | Pending | Reaching a window | Share |
|---|---:|---:|---:|
| SCC-2013-05 | 1,136 | 75 | 6.6% |
| SCC-2017-05 | 895 | 79 | 8.8% |
| **SCC-2021-05** | **836** | **146** | **17.5%** |
| ESWS-2026-05 | 717 | 66 | 9.2% |

2021 does better than any other election, by roughly double. This is the split
that currently has no news on any of its 1,639 rows and the reason the
extraction question is live at all, so the fact that it is the best-served by
extraction rather than the worst is the single most useful number here.

### By arm — local is eleven times more likely to be in-window

| Arm | Pending | Reaching a window | Share |
|---|---:|---:|---:|
| local | 1,394 | **322** | **23.1%** |
| national | 2,190 | 44 | 2.0% |

The national corpus is larger and almost none of it is close to polling day;
the local corpus is smaller and almost a quarter of it is. Of the 366 usable
articles, **322 are local and 44 are national.**

This bears directly on the finding that local news currently contributes zero
selected columns. That result comes from a pilot in which local coverage near
polling day was essentially absent — and the pending corpus is where it is.
Extraction would move the local arm from untested to testable, which is the
opposite of what the current empty result would lead one to expect.

---

## 3. Cost, and the caveat that dominates it

At the published Sonnet rates with the Batch discount and prompt caching, eight
extraction layers per article, 2,203 input tokens per article:

| Scope | Articles | Requests | USD |
|---|---:|---:|---:|
| Everything pending | 3,584 | 28,672 | **228.93** |
| **Only articles reaching a window** | **366** | **2,928** | **23.38** |
| In-window local arm only | 322 | 2,576 | 20.57 |
| In-window national arm only | 44 | 352 | 2.81 |

Extracting only what can reach a feature costs **a tenth** of extracting
everything, and loses nothing under the current window scheme, because the
3,218 excluded articles cannot enter a feature no matter what they contain.

### The caveat: this figure is a consequence of the window scheme

Every one of the 3,584 pending articles falls within 180 days of its polling
day. The collection horizon and the six-window scheme are the same 180 days, so
the entire pending corpus is in-window under that scheme and none of it is
discardable.

| Window depth | In-window | Local | National | USD |
|---|---:|---:|---:|---:|
| 30 days (current principal windows) | 366 | 322 | 44 | 23.38 |
| 60 days | 645 | 513 | 132 | 41.20 |
| 90 days | 1,037 | 753 | 284 | 66.24 |
| **180 days (six-window scheme)** | **3,584** | **1,394** | **2,190** | **228.93** |

**The window scheme decision and the extraction budget decision are the same
decision.** They have been treated as two separate open questions — one
methodological, one financial — and they are not: choosing the 30-day scheme
sets the bill at roughly 23 dollars, and choosing the six-window 180-day scheme
sets it at roughly 229. Nothing else in the pipeline moves the figure by
anything like that factor.

This is worth putting to the supervisor in exactly those terms. The window
question has been sitting as an abstract choice between three specifications;
it is actually a choice with a price attached, and framing it that way is more
likely to get a decision than restating the three schemes again.

---

## 4. What this does not settle

**In-window is necessary, not sufficient.** An article inside a window still
has to align to a ward and a party to become a feature on a row. The pilot's
alignment rate was 404 alignment records across 67 articles, but that is a
count of records rather than of articles that produced a usable row, and it has
not been measured for the pending corpus. So 366 is a ceiling on what
extraction can contribute under the 30-day scheme, not a forecast.

**The 30-day figure assumes the windows do not change later.** Extracting only
the 366 now and moving to a deeper scheme afterwards means paying for the rest
then. It is not wasted — nothing is re-extracted — but it is not the cheapest
route to that end state either, so it is only the right call if the 30-day
scheme is where the project lands.

**The cost model is an estimate.** Token counts come from stored article bytes
at four characters per token and the layer prompts are measured rather than
guessed, but the figures are projections and would move if the prompts changed.

---

## 5. What follows, now the scheme is settled

The six-window scheme is confirmed, so the whole pending corpus is in-window
and none of it can be discarded as unreachable. The distribution across the six
windows:

| Window | Pending articles |
|---|---:|
| Final 72 hours | 68 |
| 7–4 days | 43 |
| 14–8 days | 91 |
| 30–15 days | 164 |
| 90–31 days | 671 |
| 180–91 days | 2,547 |
| **Outside any window** | **0** |

Extraction is therefore priced at **$228.93** for all 3,584 articles, with no
version of the job that costs meaningfully less while still answering the
question.

**Extract in two passes rather than one.** Everything within 30 days first —
366 articles, about $23 — then the 3,218 in the two widest windows. Per-article
pricing means the two-pass route costs the same in total as one pass and
re-extracts nothing, but it puts a working end-to-end result in hand before the
larger commitment: the first pass is enough to confirm that extracted content
aligns to wards and parties and actually lands in the feature table, which is
the assumption section 4 flags as unverified. If it does not, that is far
better discovered at $23.

The first pass also happens to contain the two things most worth knowing early.
It gives the 2021 validation split 146 articles where it currently has none,
and it is 322 local articles against 44 national, so it is the pass that makes
the local arm testable at all.
