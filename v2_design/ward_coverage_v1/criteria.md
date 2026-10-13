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

(none)
