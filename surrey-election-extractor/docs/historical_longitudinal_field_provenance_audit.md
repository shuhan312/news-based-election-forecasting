# Historical and Longitudinal Fields: Provenance Audit

## Purpose

This audit separates values that can be exposed from completed official election
records from values that would require an unsupported inference. It is an
additive review of the historical-field layer; it does not change extraction,
official NULLs or the 2021-to-2026 geographic-crosswalk decision.

## Official sources reviewed

- [The Surrey (Electoral Changes) Order 2012](https://www.legislation.gov.uk/uksi/2012/1872/contents/made)
- [The Surrey (Electoral Changes) Order 2024 explanatory memorandum](https://www.legislation.gov.uk/uksi/2024/1177/pdfs/uksiem_20241177_en_001.pdf)
- [LGBCE final recommendations for Surrey (May 2024)](https://www.lgbce.org.uk/sites/default/files/2024-05/surrey_fr_long_report_-_final.pdf)
- [Surrey County Council 2017 official results announcement](https://news.surreycc.gov.uk/2017/05/05/live-election-results-declared/)
- [Surrey County Council 2021 official results announcement](https://news.surreycc.gov.uk/2021/05/07/2021-election-results/)

The 2024 explanatory memorandum identifies the 2012 arrangements as the
existing divisions that would be replaced at the May 2025 elections. The
configured audit therefore verifies two separate adjacent transitions,
2013→2017 and 2017→2021, using exactly matching published division names:
81 matches in each transition. The changed 2024/2026 boundaries remain subject
to the separate 22-relationship geographic permission audit.

## Field decisions

| Supervisor field | Decision | Evidence boundary |
| --- | --- | --- |
| Previous winning party | Materialised for 184 explicitly approved references: 81 for 2017, 81 for 2021 and 22 existing 2026 references. | Taken only from an official prior candidate row explicitly marked `Elected`; never selected by vote order. |
| Previous winning candidate | Materialised only for the same references when exactly one official `Elected` row exists. | This is a prior-result fact, not a claim that the person is a current candidate or incumbent. |
| Previous winner's candidate vote share | Materialised where the selected official elected row publishes a share. | It is a *candidate* share, never a party-total share. |
| Previous electorate and turnout | Materialised only where the permitted prior official result page publishes the value. | Missing source values remain NULL. |
| First appearance of party in area / party previously contested | Materialised for exact original party labels in the approved direct lineage. | It is first observed appearance in the project’s permitted lineage, not a claim about a party's real-world origin. |
| Previous party vote share | Remains NULL. | The result pages provide candidate shares, not a documented division-level party-total series; no party-total reconstruction is allowed. |
| Change in vote share / swing | Remains NULL. | Requires a permitted party-total comparison; the project forbids party-total reconstruction, redistribution and cross-boundary swing. |
| Candidate previously stood | Materialised as `True` only for rows in the reviewed official member-profile register; otherwise remains NULL. | The register requires a stable Surrey profile UID directly linking the exact target result page and an earlier official result page. Name-only joining remains prohibited. |
| Incumbent candidate / incumbent party | Materialised only for the same reviewed profile rows; otherwise remains NULL. | The register additionally requires a published term beginning before the target election. Incumbent party preserves the target row's exact published party label and does not infer historical affiliation. |
| Winning margin | Remains NULL. | No audited official margin field has been identified, and calculating it from candidate vote order is not permitted. |

## Conclusion

The implemented legal-continuity audit resolves a real avoidable gap: it makes
the 2013→2017 and 2017→2021 historical references available without weakening
the existing 2026 crosswalk rules. It does **not** turn the remaining personal,
party-total or swing fields into missing-data failures. Candidate history and
incumbency can now be added only through the separately reviewed official
member-profile register documented in
[`candidate_and_incumbency_evidence_audit.md`](candidate_and_incumbency_evidence_audit.md).
All other records stay visibly NULL until an authoritative source supports each
field under that method.

This is a statement about the evidence reviewed and the project’s permitted
methods, not a claim that no additional archival or returning-officer evidence
could ever exist.
