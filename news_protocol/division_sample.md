# Division Sampling Design

**Stage:** Supervisor to-do 7 (division sampling), preceding ward-level news collection (Stage C).
**Status:** Provisionally adopted pending supervisor confirmation - thresholds and algorithm below were fixed before this script was run, using only committed election-result data. Nothing about news coverage or content informed this selection.

## Pre-registered rule

- Safe: 2021 winning margin >= 20.0 percentage points
- Marginal: 2021 winning margin <= 5.0 percentage points
- Changed: 2021 and 2026 winning parties differ, restricted to the 24 division/ward pairs the project's GIS-based geographic crosswalk classifies as an 'exact' match (see surrey-election-extractor/outputs/geographic_crosswalk_resolution/) - pairs that were split, merged, or uncertain are excluded rather than approximately matched
- Reform strong: highest 2026 Reform UK vote shares (no crosswalk needed - a fact about the 2026 ward alone)
- Reform weak/absent: Reform UK not contesting in 2026, matched via the same 'exact' crosswalk against 2021 established-party strength (contrast case for the momentum-vs-conversion question)
- Per stratum: top 5 by rank (deterministic sort, no randomness); overlaps deduplicated; total constrained to 15-25 divisions

## Result: 17 divisions selected

| Division | Strata (selection evidence) |
|---|---|
| Addlestone Ward | **Reform strong** - 2026 Reform UK vote share 17.0% |
| Ashtead Ward | **Changed** - GIS-verified exact match to 2021 division 'Ashtead': winner Ashtead Independent -> Ashtead Independent, working with Ashtead Residents in 2026 (source: geographic_crosswalk_resolution/final_direct_mapping_dataset.json, relationship_type=exact) |
| Bagshot, Windlesham & Chobham Ward | **Changed** - GIS-verified exact match to 2021 division 'Bagshot, Windlesham and Chobham': winner Conservative -> Liberal Democrats in 2026 (source: geographic_crosswalk_resolution/final_direct_mapping_dataset.json, relationship_type=exact) |
| Banstead, Woodmansterne & Chipstead Ward | **Safe** - 2021 winning margin 52.8pp (Conservative held) >= 20.0pp threshold |
| Caterham Hill Ward | **Marginal** - 2021 winning margin 2.1pp (Conservative) <= 5.0pp threshold; **Changed** - GIS-verified exact match to 2021 division 'Caterham Hill': winner Conservative -> Liberal Democrats in 2026 (source: geographic_crosswalk_resolution/final_direct_mapping_dataset.json, relationship_type=exact) |
| Epsom Town & Downs Ward | **Marginal** - 2021 winning margin 0.1pp (Residents Association) <= 5.0pp threshold; **Changed** - GIS-verified exact match to 2021 division 'Epsom Town and Downs': winner Residents Association -> Liberal Democrats in 2026 (source: geographic_crosswalk_resolution/final_direct_mapping_dataset.json, relationship_type=exact) |
| Ewell Court, Auriol & Cuddington Ward | **Safe** - 2021 winning margin 52.4pp (Residents Association held) >= 20.0pp threshold; **Changed** - GIS-verified exact match to 2021 division 'Ewell Court, Auriol and Cuddington': winner Residents Association -> Residents Associations of Epsom and Ewell in 2026 (source: geographic_crosswalk_resolution/final_direct_mapping_dataset.json, relationship_type=exact) |
| Farnham Central Ward | **Safe** - 2021 winning margin 44.8pp (Farnham Residents held) >= 20.0pp threshold |
| Guildford East | **Marginal** - 2021 winning margin 1.8pp (Liberal Democrats) <= 5.0pp threshold |
| Horley West, Salfords & Sidlow Ward | **Reform strong** - 2026 Reform UK vote share 17.0% |
| Lingfield Ward | **Reform strong** - 2026 Reform UK vote share 19.0% |
| Lower Sunbury & Halliford Ward | **Marginal** - 2021 winning margin 0.7pp (Conservative) <= 5.0pp threshold |
| Redhill East | **Safe** - 2021 winning margin 44.3pp (Green held) >= 20.0pp threshold |
| Shere | **Marginal** - 2021 winning margin 1.8pp (Conservative) <= 5.0pp threshold |
| Stanwell, Stanwell Moor & Ashford North Ward | **Reform strong** - 2026 Reform UK vote share 20.0% |
| Tadworth, Walton and Kingswood | **Safe** - 2021 winning margin 58.9pp (Conservative held) >= 20.0pp threshold |
| Thorpe, Longcross & Ottershaw Ward | **Reform strong** - 2026 Reform UK vote share 17.0% |

## Confirmation needed from supervisor

The Safe/Marginal thresholds and the per-stratum target were chosen by the student to operationalise the supervisor's qualitative categories and are proposed here, not yet confirmed. To be raised at the next supervision meeting alongside protocol proposals P1-P3. Ward-level collection (Stage C) is unblocked by this file's presence but the selection may still be revised - any revision must be logged as a new version here and in the protocol deviations log, never a silent edit.
