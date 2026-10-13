# Ward-level news coverage probe: criteria (written before the run)

**Status: fixed 2026-10-13, before any matching was run.** Code:
`src/forecast/ward_coverage.py`, committed with this file. Later changes go
under Amendments.

## Why

The H2 power checks (`direction1_power`) found that the no-news model's
Reform errors lie between wards within councils, not between councils
(ICC 0%). A council-level news measure cannot reach that variation; only a
**ward-level** one could. Ward-level news is useful only if local outlets
actually cover individual contests. V1 attributed just 94 of 1,632 articles
(6%) to specific places, but that came from keyword search, not a
systematic pass over outlets. This probe measures ward coverage directly,
**on 2021 (training data)**, so that whether to pursue a ward-level news
hypothesis is decided **before** any 2025 result is opened.

## Design

- **Elections:** Kent and Surrey county councils, 6 May 2021.
- **Window:** published 90–31 days before polling day (5 Feb – 5 Apr 2021),
  V2's primary window.
- **Articles:** the six outlets of `outlet_pilot_v1` (SurreyLive, BBC Surrey,
  Surrey Comet; KentLive, BBC Kent, KentOnline), using their full cached
  Wayback lists, not a sample. Each outlet's article ids rise with
  publication date, so only ids between the last sampled article before the
  window and the first after it are fetched. The fetched publication date
  then decides window membership.
- **Contests:** every contested 2021 division, with its candidates' names,
  from Democracy Club (names and ward labels only).

## Matching (deterministic, no LLM)

An article covers a division if its headline + body contains:

- **C (candidate):** the full name ("first last") of any candidate standing
  in that division, or
- **P (place):** the division's name, or a distinctive place in it. A label
  is split on commas, "&" and "and"; generic tokens (North, South, East,
  West, Central, Rural, Town, Villages and so on) are dropped, and tokens
  shorter than 4 letters are ignored.

Place matches count only in articles that pass keyword prefilter v1 (civic
or political vocabulary), so a crime story merely naming a village does not
count. Candidate matches count in any article.

## Measures

| id | measure | role |
|---|---|---|
| **W1** | share of contested divisions with ≥ 1 covering article (C or P) | **primary** |
| W2 | share with ≥ 1 candidate-name (C) article | reported |
| W3 | share with ≥ 3 covering articles | reported: how many wards could carry a usable signal |
| W4 | articles per covered division (median) | reported |

All are reported per county and pooled.

## Decision

| W1 (pooled) | verdict |
|---|---|
| ≥ 50% | **viable:** design a pre-registered ward-level news hypothesis for 2025 (its own criteria and power check) before opening 2025 results |
| 25–50% | **marginal:** a ward-level test could only cover a minority of wards; record, and consider only with a power check showing it can pass |
| < 25% | **not viable:** ward-level news is too sparse; the news strand closes (council level: wrong resolution; ward level: too sparse) |

**Time cap:** this probe and any follow-up design take at most two working
days. If the verdict is not "viable", no further news angle is opened.

## Known limitations, stated in advance

- Wayback lists miss articles that were never archived, so coverage is a
  **lower bound**.
- Kent and Surrey 2021 had a small Reform presence. The probe measures
  whether local outlets cover individual contests at all, not Reform
  specifically.
- Name matching misses nicknames and initials, and can hit namesakes.
  Place matching can hit places that share a name.

## Amendments

**A1 (2026-10-14, after the coverage run; committed before this follow-up
is run). A follow-up measure decides whether a ward-level hypothesis is
designed.** The coverage run (`coverage_findings.md`) found that candidate
names matched are mostly sitting councillors'. A Reform cold-start test
needs coverage of candidates who are new and from outside the main
parties, as Reform's 2025 slate largely was. So the decision now rests on:

- **N1 (decisive):** among 2021 candidates who are **new** (did not stand
  for the same council in 2017) **and minor-party** (not Conservative,
  Labour or Liberal Democrat; independents included), the share named in
  at least one window article in their county.
- Reported alongside: the same share for incumbents (won in 2017), past
  candidates (stood in 2017 and lost), new major-party candidates, and
  Reform/UKIP candidates specifically.
- Code: `src/forecast/candidate_coverage.py`, which uses the same window
  articles and the same full-name rule as the coverage run.

| N1 | decision |
|---|---|
| ≥ 50% | design a pre-registered ward-level news hypothesis, with its own power check, before any 2025 result is opened |
| 25–50% | design only if the power check, run with this sparsity, can pass |
| < 25% | **stop**: ward-level news would leave most 2025 Reform wards empty; the news strand closes |

This is the last news check under the two-day cap.

**A2 (2026-10-14). A measurement flaw, found after the A1 result; the
corrected measurement is fixed before it is run.**

- *When:* after N1 = 4.2% ("stop") was committed (9638a96). Recorded as
  found after the result.
- *What:* N1 was measured on articles published 90–31 days before polling
  day (5 Feb – 5 Apr 2021). The official statements of persons nominated
  were published on **9 April 2021**. For example, Kent's for Ashford
  Central is dated "Friday 9 April 2021" (checked from the PDF Democracy
  Club holds). New candidates were not yet public candidates anywhere in
  that window, so naming them there was structurally unlikely; incumbents
  were named because they are councillors anyway. The window cannot
  measure what N1 asks.
- *Why it is a correction:* it rests on an institutional fact, the
  nomination timetable, and would be made whichever way it moved N1. The
  measure, the matching rule and the thresholds are unchanged.
- *Corrected measurement:* articles published **30–1 days before polling
  day (6 Apr – 5 May 2021)**, from the campaign after nominations. Same six
  outlets and article-id method. Wayback captures are listed up to 31 May
  2021 so that late-April articles archived after polling day are found;
  only articles **published** in the window are used. 2021 is training
  data, so a post-polling-day capture of a pre-election article raises no
  leakage concern. Code: `--window late` in `forecast.ward_coverage` and
  `forecast.candidate_coverage`.
- *Decision:* the A1 rule applies to the corrected N1. If N1 < 25%, the
  news strand closes **with no further angle**. If a ward-level hypothesis
  is designed, its 2025 news features also use the 30–1 day window, which
  is still entirely before polling day.
- *Reporting:* both N1 values are reported. If the decision changes, the
  report says the change came from a post-result measurement correction.
- *Known limitation, not correctable:* 2021 was a COVID campaign
  (door-to-door canvassing resumed only on 8 March), so coverage may be
  lower than in a normal year.

**A3 (2026-10-14). The decisive measurement moves from a 2021 proxy to
2025's actual Reform candidates. Fixed before any A2 or A3 figure is
computed.**

- *Why:* N1 asks whether local news names the kind of candidate Reform
  fielded in 2025. 2021 is a weak proxy: Reform/UKIP had 27 candidates in
  Kent and Surrey combined, Reform polled about 2%, and it was a COVID
  campaign. The real quantity is measurable directly, because **2025
  pre-election news and the 2025 candidate list are pre-election
  information, not results**. Reading them leaves the 2025 test blind.
- *Decisive measure R1:* the share of Kent's 2025 Reform UK candidates
  named in at least one local article **published 30–1 days before polling
  day (1–30 April 2025)**. Statements of persons nominated were published
  in early April, inside the window. Outlets: KentLive (`/news/`), BBC Kent
  and KentOnline (town sections), as in `outlet_pilot_v1`.
- *Naming rule:* the candidate's full name, **or** their surname (at least
  4 letters) within 100 characters of the word "Reform". The second form
  catches "Reform candidate Smith said …"; the proximity requirement
  limits false hits on common surnames.
- *Blinding:* the 2025 candidate list is read from Democracy Club, whose
  response also carries results. The code keeps only ballot, person id,
  name and party, discards every result field at read time, and never
  stores or prints a vote count or an elected flag. A test enforces this.
  Articles are used only for name matching; no article text is printed.
  Wayback captures are listed to 31 May 2025 to catch archive lag; only
  articles **published** by 30 April count.
- *Decision:* as A1, applied to R1: ≥ 50% design a ward-level hypothesis;
  25–50% only if its power check can pass; < 25% the news strand closes,
  with no further angle.
- *Supporting, not decisive:* 2021 N1 on the corrected window (A2), and the
  share of new (not standing for Kent in 2021) Reform candidates named.
- *Implementation fixes made before any result (A2 code):* the late-window
  id bounds first dropped SurreyLive entirely (a cap from a sample ending
  in March), then Surrey Comet and KentOnline (a misread sample date made
  the lower bound exceed the upper). The bounds now start from the
  validated original lower bound with no upper bound, and the run stops if
  any outlet has no targets.
- *Reporting:* 2021 N1 (main window), 2021 N1 (late window) and R1 are all
  reported.

**A4 (2026-10-14). Candidate-list articles are excluded from R1. Found
after the 2021 late-window N1 was computed, and fixed before R1 is
computed.**

- *What happened:* 2021 late-window N1 came out at 41.3% (Reform/UKIP
  33.3%), but only 1.4% of new minor-party candidates were named three or
  more times. Most naming came from candidate-list articles. One SurreyLive
  article ("Surrey County Council Elections 2021: Who represents me and who
  can I vote for?") names 251 candidates; three district lists name 10–16
  each. Excluding articles that name 10 or more candidates, N1 is 12.6%
  (Reform/UKIP 11.1%; incumbents 54.8% → 24.0%).
- *Why lists must not count:* a list says only that a person is standing,
  which the official candidate list already says. It carries no stance,
  issue or event about the candidate, so it cannot feed any news feature.
  Counting it would overstate what news offers, which is exactly the error
  V2 exists to avoid.
- *Rule for R1:* a Reform candidate counts as named only through an
  article that names **fewer than 10** of Kent's 2025 candidates (any
  party), by the A3 naming rule. Lists are identified by this count alone,
  which is mechanical and is fixed before R1 is seen.
- *Decision:* the A1/A3 thresholds apply to R1 with lists excluded. R1
  including lists is reported alongside but is **not** used for the
  decision.
- *2021 supporting figures* are reported both ways: main window 4.2%; late
  window 41.3% with lists, 12.6% without.
