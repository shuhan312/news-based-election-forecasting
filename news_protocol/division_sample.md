# Division Sampling Design

**Stage:** Supervisor to-do 7 (division sampling), preceding ward-level news collection (Stage C).
**Status:** Provisionally adopted pending supervisor confirmation - thresholds and algorithm below were fixed before this script was run, using only committed election-result data. Nothing about news coverage or content informed this selection.

## Pre-registered rule

- Safe: 2021 winning margin >= 20.0 percentage points
- Marginal: 2021 winning margin <= 5.0 percentage points
- Changed: 2021 and 2026 winning parties differ (2026 ward boundaries; crosswalk to 2021 divisions pending)
- Reform strong: highest 2026 Reform UK vote shares
- Reform weak/absent: Reform UK not contesting in 2026, matched against 2021 established-party strength (contrast case for the momentum-vs-conversion question)
- Per stratum: top 5 by rank (deterministic sort, no randomness); overlaps deduplicated; total constrained to 15-25 divisions

## Result: 10 divisions selected (2026 data not yet available - Changed and Reform strata pending, see note below)

| Division | Strata (selection evidence) |
|---|---|
| Banstead, Woodmansterne and Chipstead | **Safe** - 2021 winning margin 52.8pp (Conservative held) >= 20.0pp threshold |
| Caterham Hill | **Marginal** - 2021 winning margin 2.1pp (Conservative) <= 5.0pp threshold |
| Epsom Town and Downs | **Marginal** - 2021 winning margin 0.1pp (Residents Association) <= 5.0pp threshold |
| Ewell Court, Auriol and Cuddington | **Safe** - 2021 winning margin 52.4pp (Residents Association held) >= 20.0pp threshold |
| Farnham Central | **Safe** - 2021 winning margin 44.8pp (Farnham Residents held) >= 20.0pp threshold |
| Guildford East | **Marginal** - 2021 winning margin 1.8pp (Liberal Democrats) <= 5.0pp threshold |
| Lower Sunbury and Halliford | **Marginal** - 2021 winning margin 0.7pp (Conservative) <= 5.0pp threshold |
| Redhill East | **Safe** - 2021 winning margin 44.3pp (Green held) >= 20.0pp threshold |
| Shere | **Marginal** - 2021 winning margin 1.8pp (Conservative) <= 5.0pp threshold |
| Tadworth, Walton and Kingswood | **Safe** - 2021 winning margin 58.9pp (Conservative held) >= 20.0pp threshold |

## Outstanding: 2026 data dependency

`data/elections/2026_east_surrey_results.csv` and `2026_west_surrey_results.csv` do not exist yet. Run `python3 src/fetch_2026_surrey_results.py` to produce them, then re-run this script (`python3 src/build_division_sample.py`) to populate the Changed and Reform strata and finalise the sample.

## Confirmation needed from supervisor

The Safe/Marginal thresholds and the per-stratum target were chosen by the student to operationalise the supervisor's qualitative categories and are proposed here, not yet confirmed. To be raised at the next supervision meeting alongside protocol proposals P1-P3. Ward-level collection (Stage C) is unblocked by this file's presence but the selection may still be revised - any revision must be logged as a new version here and in the protocol deviations log, never a silent edit.
