# N5 data requirements and risks (identifiability audit record)

Live audit outputs: `outputs/n5_specification/` (regenerate with
`scripts/run_n5_specification_audit.py`; deterministic, no network).

## What the real release supports

| Question | Audit answer |
| --- | --- |
| Complete Dirichlet compositions | **258** of 339 contests (all single-member; shares close within the extractor's own 98-102 tolerance) |
| Excluded contests | 81, all `multi_member_party_share_estimand_undefined` (2026 wards) — an estimand boundary, not missing data |
| Election-cycle effect | 18 events: the 3 principal elections (81 contests each) support individual cycle effects; all 15 by-elections are singletons, identifiable only through pooling. Election type is perfectly confounded with cycle size (every singleton is a by-election), so a cycle effect and a by-election fixed effect must not both be free parameters without a constraint. |
| Party effects | 35 continuing parties audited (candidate-specific Independents excluded by identity rule). **6** support individual intercepts: Conservative (254 contests), Liberal Democrats (239), Labour (219), UKIP (150), Green (111), Labour & Co-operative (26). The remaining 29 require partial pooling. |
| **Reform UK specifically** | 13 usable contests, 8 events, 13 areas, 2021-2026: **not individually identifiable — partial pooling is mandatory.** The party the supervisor's questions centre on is exactly the cold-start case a hierarchical prior exists to serve; UKIP's 150-contest history remains a separate key and must never leak into Reform UK's effect. |
| Area effects | 83 stable areas; **81 have 3+ usable, safely linked compositions** (stable 2013-2021 division geography), 2 have one. An area effect (N5b) is empirically supported for those 81 areas — more support than initially assumed — but never for 2026 wards, whose geography is excluded from safe linkage. |
| Structural zeros | The release contains **zero** structural-non-participation rows: a party absent from a ballot has no row. A ballot-restricted softmax/Dirichlet therefore handles structural zeros by construction; no epsilon substitution is permitted or needed. Participating multi-member rows with undefined targets (464) and geography-incomparable targets (680) reuse the existing authoritative states; no new missingness taxonomy was created. |

## Principal risks, in order of concern

1. **Cycle/type confounding** (above): fix by treating by-elections
   through one shared indicator plus pooled cycle noise, not free
   per-event effects.
2. **sigma_area vs phi competition** in N5b: 3-4 observations per area is
   enough to include the term, not enough to make it cheap; divergence
   and R-hat checks are mandatory per fold, and N5b is conditional on
   N5a's clean convergence.
3. **Early-fold sparsity**: the first evaluable folds train on 2013 only
   (81 compositions); posterior intervals there will be wide, and that is
   the honest answer, not a defect.
4. **Precision misspecification**: phi controls interval width globally;
   interval-coverage diagnostics (50%/90%) are the check, and they must
   be reported per fold, not only pooled.

## Unresolved decisions (for supervisor discussion, not silent choices)

- Whether N5 is implemented at all before news collection begins: the
  no-news ladder (N0-N4) is complete and frozen; N5's marginal value is
  calibrated uncertainty, at a real implementation and computation cost.
- Reference-party constraint choice for softmax identifiability (fixed
  reference vs sum-to-zero), which affects intercept interpretability.
- Whether `Labour` and `Labour and Co-operative` share a hierarchical
  parent: they are distinct published labels in the release and stay
  distinct by default; any grouping would need the same evidence
  standard as every other identity decision in this repository.
