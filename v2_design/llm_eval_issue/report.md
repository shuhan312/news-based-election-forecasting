# llm_eval report: primary issue (V1 issues layer, claude-sonnet-5)

**Verdict: PASS, with a provenance flag (read section 1).** 53 labelled pairs, categories: candidate_party_conduct, council_finance, council_performance, council_tax, crime_policing, election_administration, environment_flooding, healthcare, immigration, investment_funding, local_business, local_government_reorganisation, national_economy, national_politics, none, other, planning_housing, resignation_defection, roads_transport, scandal, schools_send, service_closure, social_care, voter_switching.

## 1. Reference labels

- **Provenance:** Reference labels were made with AI assistance; agreement with an LLM is consistency with that standard, not independent validation. (53 of 53 labels)

## 2. Scores (95% bootstrap CI)

| metric | value |
|---|---|
| kappa | 0.616 [0.483, 0.748] |
| accuracy | 0.641 [0.509, 0.774] |
| macro_f1 | 0.606 [0.491, 0.731] |

| category | recall |
|---|---:|
| candidate_party_conduct | 0.000 |
| council_finance | 1.000 |
| council_performance | 0.000 |
| council_tax | 1.000 |
| crime_policing | 0.500 |
| election_administration | 0.000 |
| environment_flooding | 1.000 |
| healthcare | 0.833 |
| immigration | 1.000 |
| investment_funding | 0.000 |
| local_business | 1.000 |
| national_economy | 1.000 |
| national_politics | 0.833 |
| other | 0.000 |
| planning_housing | 1.000 |
| resignation_defection | 0.000 |
| roads_transport | 0.333 |
| scandal | 1.000 |
| schools_send | 1.000 |
| service_closure | 1.000 |
| social_care | 1.000 |
| voter_switching | 0.000 |

## 3. Gate

| metric | value | bar | result |
|---|---:|---:|---|
| kappa | 0.6164 | 0.6 | pass |

## Subgroups by `group`

| group | n | kappa | accuracy |
|---|---:|---|---|
| local | 27 | 0.470 [0.273, 0.650] | 0.518 [0.333, 0.704] |
| national | 26 | 0.741 [0.554, 0.911] | 0.769 [0.615, 0.923] |
