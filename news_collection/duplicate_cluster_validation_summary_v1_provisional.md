# Duplicate-cluster validation - Step 6 summary (v1 provisional)

* rules: `cluster-validation-v1.0-2026-07-26`
* authoritative inputs: `layer=normalised-text-v1_provisional;exact=exact-dup-v1.0;url=url-canon-v1.0-2026-07-27;near-dup=near-dup-v1.0-2026-07-26;syndication=syndication-v1.0-2026-07-26;version=version-link-v1.0-2026-07-26`
* evidence graph: 1546 articles, 305 typed edges; dispositions {'linking': 11, 'non_linking': 292, 'blocked': 2}
* validated families: 4 by type {'same_article_version_family': 4}; status {'validated_retained': 4}
* conflict-rule applications: 2
* review queue: 0 families
* article status: {'independent_article': 1538, 'in_validated_family': 8} (reconciled: 8 in families + 1538 independent = 1546)

Relationship types were never flattened; blocked and superseded edges remain recorded with their blocking rule. Syndication stays a separate layer from same-article families. Member temporal availability is copied verbatim from Step 5 - validation altered no availability decision and no prediction-window flag. No record was deleted, merged or suppressed.
