# County-level history features: construction and measured effect

**Recorded 29 July 2026.** Six features the brief's list names and the
candidate contract could not hold, plus the experiment that shows what adding
them actually does. The result is mixed and one part of it is bad, which is
why it is written down here rather than summarised as an improvement.

---

## Why they were built

The SHAP decomposition of the selected model showed Reform UK pushed below the
equal split by every historical feature the model held, because in most
divisions it has no `previous_party_vote_share` at all. Reform does have
history — six divisions in 2021 and nine by-elections since — but it is
**county-level**, and every existing historical feature is division-level.

The brief's feature list names exactly this gap:

> years since previous contest; historical party strength; party-level recent
> performance based only on earlier elections; local-area historical
> performance based only on permitted mappings

## What was built

| feature | definition |
| --- | --- |
| `party_county_strength_previous` | contest-weighted mean vote share across the county in earlier elections |
| `party_county_strength_trend` | change against the preceding window |
| `party_contests_fought_previous` | distinct areas fought, not candidate rows |
| `party_contest_rate_previous` | share of available contests the party chose to fight |
| `years_since_previous_comparable_election` | gap to the approved predecessor contest |
| `area_parties_in_previous_contest` | distinct political identities in the predecessor contest |

### Two construction decisions that changed the result

**The mean is over contests fought, not contests available.** Averaging in
zeros for divisions a party declined to contest conflates how well it does
where it stands with how widely it stands. The second is published separately
as `party_contest_rate_previous`, which is a signal in its own right: Reform
moved from 7 per cent of divisions in 2021 to 100 per cent in 2026.

**Contests pool across elections rather than being counted within one.** The
first version required three contests inside a single election, which silently
excluded every by-election, because a by-election has one. For Reform that was
not a rounding error: its county strength stayed frozen at 2021's 2.83 per
cent through nine later by-elections in which it polled 7 to 34 per cent. A
feature built to show a party rising instead pinned it to its weakest recorded
year. Pooling backwards until three contests accumulate, inside a five-year
window and weighted by contests, fixes it:

| target election | county strength | trend |
| --- | ---: | ---: |
| 2022-11-30 | 2.83% | — |
| 2025-05-01 | 3.43% | — |
| 2025-07-10 | 5.88% | — |
| 2025-08-21 | 16.33% | +13.5 |
| 2025-10-16 | 22.00% | +16.1 |
| **2026-05-07** | **20.67%** | −1.33 |

### Coverage

| | rows | strength | trend |
| --- | ---: | ---: | ---: |
| all | 1,992 | 1,459 | 1,160 |
| **Reform UK** | 178 | **172** | **169** |
| UKIP | 151 | 70 | 61 |

A null strength means no qualifying earlier record, never a strength of zero.

## The measured effect, on the 2026 holdout

| architecture | | MAE | winner | Reform predicted | Reform vs equal split |
| --- | --- | ---: | ---: | ---: | ---: |
| A regularised linear | before | 4.78 | 29.3% | 8.40% | −16.7% |
| A regularised linear | **after** | 5.09 | 28.0% | **6.96%** | **−42.6%** |
| C partial pooling | before | 4.89 | 30.5% | 8.91% | −15.8% |
| C partial pooling | **after** | **4.65** | **41.5%** | 7.53% | **−31.6%** |
| B gradient-boosted trees | before | 4.78 | 32.9% | 9.44% | −12.4% |
| B gradient-boosted trees | **after** | **4.53** | 30.5% | 9.35% | **−11.1%** |

Observed Reform mean share: 10.80 per cent.

### The bad part, stated plainly

**On Reform UK the two linear architectures get substantially worse.**
Architecture A moves from 16.7 to 42.6 per cent worse than an equal split, and
Architecture C from 15.8 to 31.6 per cent. Both predict Reform *lower* after
being given a feature that says Reform has been polling 20 per cent — the
opposite of the intended effect.

The likely mechanism, which is a hypothesis rather than a measured finding:
for almost every party, county strength and division vote share are strongly
positively related — the Conservatives poll around 30 per cent county-wide and
around 30 per cent in a division. Reform is the exception: 20.67 per cent
county-wide from single-member by-elections, against 10.80 per cent in
two-member wards where its support is split across two ballot lines and the
denominator is larger. A linear model fits one global slope for the
relationship and applies it to Reform, which moves Reform the wrong way.

This is the same failure the SHAP analysis found for
`previous_party_vote_share`: a feature whose effect is **conditional on
party**, which a linear model can only average and a tree can condition on.
It is now the second independent piece of evidence that the brief's
requirement to "permit interactions between Reform UK and relevant historical
predictors" is a necessity here rather than an option.

### The good part

Overall error improves for the two architectures that can use the features
non-linearly or with party-specific shrinkage. Architecture C's winner
accuracy rises from 30.5 to 41.5 per cent, the largest single improvement
measured in this project. Architecture B, the selected architecture, improves
on both overall MAE (4.78 to 4.53) and Reform (−12.4 to −11.1 per cent), and
remains the only configuration whose Reform predictions are within 12 per cent
of an equal split.

## What follows from this

1. The features are retained. The selection mechanism uses Reform vote-share
   MAE as its primary criterion, so it will prefer the architecture that
   handles them best rather than the one that is hurt by them.
2. Reform-specific interaction terms are now justified by evidence rather than
   by the brief alone, and are the next thing to build.
3. Any claim that these features "improved the model" must state which
   architecture. On Architecture A they made it worse.

## Leakage controls

Every value is computed from elections polled **strictly before** the row's
own date, and never from the embargoed 7 May 2026 holdout even though it is
genuinely earlier than the 7 July Haslemere by-election — the brief asks for
Haslemere to be predicted "without using any 7 May 2026 results", and a
strength sourced from 7 May would couple two holdouts meant to be independent.

The guard verifies the **property**, not the arithmetic. Each row records
which elections it pooled; the check reads those identifiers back and asserts
their dates. An earlier version recomputed the value with its own copy of the
construction, which only established that the code agreed with itself — and
duly failed when the construction changed from single-election to pooled,
against nothing more than its own obsolete formula.

---

## Related records

- [`candidate_model_card.md`](candidate_model_card.md) — the SHAP finding that
  motivated these features
- [`candidate_split_and_leakage.md`](candidate_split_and_leakage.md) — the
  date rules these features obey
