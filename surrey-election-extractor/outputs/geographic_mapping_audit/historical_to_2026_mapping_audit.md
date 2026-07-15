# Surrey Historical-to-2026 Geographic Mapping Evidence Audit

- Audit status: `reference_bridge_ready`
- Verified Geographic Mapping rows created: 0
- Historical comparisons allowed: False

## Historical election coverage

- surrey-county-council-2013: 81 published divisions/areas; 358 candidate records.
- surrey-county-council-2017: 81 published divisions/areas; 377 candidate records.
- surrey-county-council-2021: 81 published divisions/areas; 331 candidate records.

## 2026 election coverage

- surrey-county-council-2026-east-surrey: 36 published wards/areas; 379 candidate records.
- surrey-county-council-2026-west-surrey: 45 published wards/areas; 453 candidate records.

## Reviewed evidence

- [Surrey (Structural Changes) Order 2026](https://www.legislation.gov.uk/ukdsi/2026/9780348278507/pdfs/ukdsi_9780348278507_en.pdf) — Articles 47(2)(c) and 49(2)(c), with Schedules 1 and 2, state that each new 2026 ward has the same area as the county council electoral division of that name under the 2024 Order. Historical crosswalk: `False`; 2026-to-2024 bridge: `True`; official geometry: `False`.
- [LGBCE Surrey final mapping files, May 2024](https://www.lgbce.org.uk/sites/default/files/2024-05/surrey_mapping_files.zip) — The completed LGBCE Surrey review publishes official final mapping files for the 2024 electoral divisions. Historical crosswalk: `False`; 2026-to-2024 bridge: `False`; official geometry: `True`.
- [Surrey County Council Electoral Division GIS layer](https://sccmaps.surreycc.gov.uk/webmaps/rest/services/SCC_Data_ForSharedUse/AdminBoundaries/MapServer/7) — The official public ArcGIS layer exposes 81 Electoral Division features with published names, geometry, version and availability fields. Historical crosswalk: `False`; 2026-to-2024 bridge: `False`; official geometry: `True`.

## Decision

The 2026 Order provides an official legal bridge from each 2026 ward to a same-area 2024 electoral division. It does not identify an individual 2013, 2017 or 2021 division as the same geography as a 2026 ward. Therefore no historical Geographic Mapping rows have been written and no historical comparison or enrichment is permitted.

## Required next evidence

A reviewed GIS-overlay crosswalk, based on the official historical division geometry and the official 2024 geometry, that records each specific historical division/current ward overlap and source evidence.
