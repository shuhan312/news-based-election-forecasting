# Surrey Geographic Mapping Decision Methodology

## Legal identity is not analytical comparability

A GIS direct match may be analytically comparable even where administrative identity is not_confirmed. This does not state that the areas are legally identical. A direct legal crosswalk would be required to set administrative identity to confirmed.

## Direct analytical acceptance rules

A direct analytical match requires at least 99.85% coverage in both directions and no competing historic or current area with 0.1% or more overlap. The 99.85% tolerance is calibrated against the LGBCE's official statement that 24 Surrey divisions stay the same: it admits the two no-material-competitor pairs affected by sub-0.15% GIS boundary precision differences, while the next candidate remains below threshold. These thresholds are applied to GIS evidence only and do not claim administrative identity.

Names are retained for audit but are never used as an acceptance criterion.

## Relationship handling

- exact and near_exact: may be accepted_direct only when every configured GIS rule passes.
- split and merged: not comparable as one-to-one; separate aggregate methodology would be required.
- uncertain and failed direct criteria: remain requires_review.

## Limitations

GIS overlap alone cannot establish legal identity, comparable electorates or a valid political comparison. This framework therefore exposes only accepted_direct rows to a future separately authorised enrichment stage and calculates no historical features.
