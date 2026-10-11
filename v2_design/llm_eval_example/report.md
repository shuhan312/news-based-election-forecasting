# llm_eval report: local_relevance (V1 frozen classifier, B0)

**Verdict: PASS, with 3 reference-label audit flags (read section 1).** Split `test`, n = 166 (60 positive). Predictions: `archived`.

## 1. Reference-label audit

Read this first: a flag here changes what the scores below mean.

- **Rule mismatch** in batch `v1_validation_seen` (stratum `local`, label 1): 31 of 39 labels use a reason code outside the stratum's rules: {'E5-N1-PARTY-POLITICS': 12, 'E5-N2-POLICY-ISSUE': 18, 'E5-N3-REFORM-GROWTH': 1}
- **Base-rate drift** for source_id `guardian_api`: positive rate 19% in `corpus_manual` vs 81% in `v1_validation_seen` (n = 247, 42; Fisher p = 8.6e-15)
- **Provenance:** Reference labels were made with AI assistance; agreement with an LLM classifier is consistency with that standard, not independent validation. (380 of 380 labels)

## 2. Scores (95% bootstrap CI)

| metric | value |
|---|---|
| kappa | 0.703 [0.579, 0.810] |
| recall | 0.833 [0.732, 0.921] |
| precision | 0.794 [0.685, 0.883] |
| f1 | 0.813 [0.727, 0.881] |
| agreement | 0.861 [0.801, 0.910] |

## 3. Gate

| metric | value | bar | result |
|---|---:|---:|---|
| kappa | 0.7031 | 0.6 | pass |
| recall | 0.8333 | 0.75 | pass |

## Subgroups by `source_id`

| group | n | kappa | recall | precision |
|---|---:|---|---|---|
| bbc_surrey | 10 | 0.286 [0.000, 0.783] | 0.500 [0.134, 0.875] | 1.000 [1.000, 1.000] |
| guardian_api | 123 | 0.593 [0.381, 0.759] | 0.783 [0.608, 0.941] | 0.600 [0.403, 0.786] |
| guildford_dragon | 5 | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| surrey_comet | 2 | 0.000 [0.000, 0.000] | n/a | n/a |
| surreylive | 26 | 0.458 [-0.067, 1.000] | 0.958 [0.855, 1.000] | 0.958 [0.870, 1.000] |
