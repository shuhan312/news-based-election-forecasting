# llm_eval report: stance per party (V1 revised layer, claude-sonnet-5)

**Verdict: PASS, with a provenance flag (read section 1).** 71 labelled pairs, categories: favourable, neither, unfavourable.

## 1. Reference labels

- **Provenance:** Reference labels were made with AI assistance; agreement with an LLM is consistency with that standard, not independent validation. (71 of 71 labels)

## 2. Scores (95% bootstrap CI)

| metric | value |
|---|---|
| kappa | 0.736 [0.584, 0.864] |
| accuracy | 0.845 [0.761, 0.915] |
| macro_f1 | 0.858 [0.763, 0.930] |

| category | recall |
|---|---:|
| favourable | 1.000 |
| neither | 0.630 |
| unfavourable | 0.971 |

## 3. Gate

| metric | value | bar | result |
|---|---:|---:|---|
| kappa | 0.7361 | 0.6 | pass |

## Subgroups by `group`

| group | n | kappa | accuracy |
|---|---:|---|---|
| conservative | 20 | 0.663 [0.214, 1.000] | 0.850 [0.650, 1.000] |
| green | 6 | 0.700 [0.000, 1.000] | 0.833 [0.500, 1.000] |
| labour | 21 | 0.667 [0.364, 0.923] | 0.809 [0.619, 0.952] |
| liberal_democrat | 10 | 0.649 [0.000, 1.000] | 0.800 [0.500, 1.000] |
| reform_uk | 9 | 0.609 [0.000, 1.000] | 0.889 [0.667, 1.000] |
| ukip | 5 | 1.000 [0.000, 1.000] | 1.000 [1.000, 1.000] |
