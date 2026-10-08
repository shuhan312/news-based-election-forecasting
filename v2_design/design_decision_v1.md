# V2 design decision: where can a content signal come from?

**2026-10-08. A decision record.** It summarises what the V2 design work has
established, compares three directions, recommends one, and names the first
task. The evidence lives in the folders cited below.

## What has been established

| finding | source |
|---|---|
| Detecting a content effect needs tens of independent election units. Surrey alone cannot do it | `power_v1` |
| Static party indicators do not transfer between elections. V1's +0.83pp party gain is probably specific to 2026 | `power_v1` |
| Out of sample, tone hurts (−0.54pp). The incumbent-judgement frame leans positive (+0.31pp, CI touches 0) | `power_v1` |
| National coverage is identical for every council voting on the same day. More councils add no national signal | `feasibility_probe_v1` |
| Election results for other councils are complete and free (Democracy Club) | `feasibility_probe_v1` |
| Local relevance screening works on consistently labelled data. The keyword prefilter keeps every V1 feature article and removes ~75% of outlet output | `local_relevance_v1`, `keyword_prefilter_v1` |
| **Local outlets cover council services, not parties.** 1 of 13 relevant local articles named a main party | `outlet_pilot_v1` |

The original V2 plan (many councils × party-named local news) fails on the
last row. Whatever V2 tests must draw its signal from where the data actually
is.

## Three directions

### A. Incumbent performance (local)

Attribute council-service coverage (bins, planning, roads, budgets, council
meetings) to the party **controlling** the council. Measure how much of it
there is and whether it is favourable or unfavourable. Test whether that
predicts the controlling party's vote-share change beyond history, national
polling and coverage volume.

- **Unit:** one council-election, i.e. the controlling party in one council
  at one election. English county and unitary rounds (2017, 2021, 2025)
  supply several dozen.
- **Why it can work:** this coverage is abundant (KentOnline: 8 of 9
  classified articles relevant). It varies by council, which national
  coverage does not. It carries information polls cannot see: local
  performance. It is the direction of the only positive content lead.
- **Risks:** an attribution rule is needed (who controlled which council
  when), plus a validated favourable/unfavourable judgement on council
  performance. One unit yields one signal, not five parties.

### B. Many election dates (national)

Use English council by-elections, which are spread across hundreds of dates
a year. Test whether national party coverage in the weeks before each date
predicts the swing beyond national polling.

- **Why it can work:** many independent dates. V1's Guardian pipeline already
  collects national coverage. Results are on Democracy Club.
- **Risks:** by-elections are single wards dominated by local factors, so
  outcomes are very noisy. National polls already summarise national mood,
  so the incremental content effect is likely near zero. That is a valid
  result, but a weak one to build a project on.

### C. A and B combined

The most complete design, and roughly double the work. Worth it only once A
or B has shown a signal.

## Recommendation: A first

1. It is the only direction where V2's data advantage (local, council-varying
   coverage) meets a plausible effect (local performance that polls do not
   see).
2. It builds directly on V1's strongest content lead, and turns the pilot's
   negative finding (local news does not name parties) into a design.
3. As a portfolio story it is the strongest: a failed premise, diagnosed with
   data, leading to a reformulated estimand.

B stays as a later, cheap extension. Its national pipeline already exists.

## First task under A: a results-only power check (free)

Before any news is collected, establish whether direction A **can** detect
an effect of plausible size. This uses election results only (Democracy
Club), with no news and no API cost:

1. Build the outcome: the controlling party's vote-share change per
   council-election, for English county and unitary rounds.
2. Model it with history and national polling only (the baseline V2 must
   beat), and measure the residual spread across councils.
3. From that spread and the number of available council-elections, compute
   the smallest content effect detectable at 80% power.
4. **Decision:** if the detectable effect is plausible (say, a percentage
   point or two of incumbent swing), proceed to build the attribution and
   performance-tone pipeline. If it is not, stop direction A before spending
   anything on news.

This repeats the logic that has worked throughout V2: test the riskiest
assumption first, with the cheapest data that can falsify it.
