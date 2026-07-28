# Historical and longitudinal fields: provenance audit

## Purpose

This audit records which longitudinal values are available, which evidence
authorises them and which inferences remain prohibited. It does not overwrite
official source fields or permit vote redistribution across changed geography.

## Authoritative continuity evidence

- [The Surrey (Electoral Changes) Order 2012](https://www.legislation.gov.uk/uksi/2012/1872/contents/made)
- [The Surrey (Electoral Changes) Order 2024 explanatory memorandum](https://www.legislation.gov.uk/uksi/2024/1177/pdfs/uksiem_20241177_en_001.pdf)
- [LGBCE final recommendations for Surrey (May 2024)](https://www.lgbce.org.uk/sites/default/files/2024-05/surrey_fr_long_report_-_final.pdf)
- Official Surrey principal-election and by-election result pages retained in
  the master payload.

The release contains 204 approved predecessor relations: 81 for 2013→2017, 81
for 2017→2021, 15 same-statutory-division by-election relations and 24 reviewed
2021→2026 direct geographic relations. Partial, unapproved or non-comparable
crosswalks remain blocked.

## Field decisions

| Supervisor field | Current release | Evidence boundary |
| --- | --- | --- |
| Previous winning party | 201/339 area rows | Single prior official candidate row explicitly marked `Elected` under an approved relation; never selected by vote order. |
| Previous winning candidate | Same approved relations when exactly one prior elected row exists | A prior-result fact, not automatic proof of current identity. |
| Previous winner candidate share | Published share of that prior elected row | Candidate share, not reconstructed multi-candidate party total. |
| Previous electorate and turnout | Available only where the approved prior official result publishes the value; no-news turnout may use separately cited supplementary official evidence | Missing source values remain `NULL`. |
| Previous party vote share | 1,037/1,987 candidate rows | The unique prior candidate share for the current row's exact published party label in an approved single-member lineage. A zero is allowed only when the complete prior candidate table proves label absence. No party aggregation or fuzzy label mapping. |
| Change in vote share | 791/1,987 candidate rows | Current analysis share minus approved prior exact-label share. Post-election diagnostic only; excluded from the no-news baseline. |
| Party previously contested / first observed appearance | 1,055/1,987 candidate rows | Exact published labels inside approved lineages. “First” means first observed in that permitted project lineage. |
| Candidate previously stood | 355 True; 1,274 False; 358 Unknown | Complete chronological prior official candidate universe with exact complete-name linkage; no fuzzy matching. All Unknown rows are 2013 first-period records. |
| Incumbent candidate | 115 Yes; 1,514 No; 358 Unknown | Complete official pre-election councillor roster reconstructed from principal results and intervening by-elections. All Unknown rows are 2013. |
| Incumbent party | 170 Yes; 627 No; 1,190 Unknown | Exact current/prior party label comparison only for an approved comparable area. Two-member or altered geography remains Unknown. |
| Winning margin | 0 official; 339 labelled analysis values | 258 single-seat runner-up gaps and 81 two-member final-seat cutoff gaps. Twenty-eight 2021 areas use separately cited statutory Seats evidence. |
| Final position | 0 official; 1,971 derived competition ranks | Complete same-page official votes; eight tied rows retain tie flags. Derived rank never becomes official rank. |

## Modelling boundary

`previous_party_vote_share`, previous winner information, previous turnout and
previous electorate are lagged features. `change_in_vote_share`, current vote
share, current outcome, rank and winning margin contain the target election
result and are prohibited from the no-news predictor.

The current division-level no-news export contains 201 eligible predecessor
rows and 138 rows without an approved predecessor. It does not yet publish the
candidate/party-level lagged-share table, so no-news publication remains a
separate downstream task even though the election master contains the required
1,021 values.

## Conclusion

The election master now exposes the maximum defensible longitudinal coverage
within its declared 2013--2026 scope. Remaining `NULL` values are first-period,
identity, source-publication or geographic-comparability boundaries. Additional
values require new authoritative evidence or an explicitly approved method;
they must not be created by fuzzy identity matching, party merging or boundary
vote redistribution.
