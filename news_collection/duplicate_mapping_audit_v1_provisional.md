# Duplicate mapping layer - Step 8 audit (v1 provisional)

* snapshot date: 2026-07-26 | rules: `dup-mapping-v1.0-2026-07-26` | git: `b413a07`
* authoritative inputs: `layer=normalised-text-v1_provisional;url=url-canon-v1.0-2026-07-27;near-dup=near-dup-v1.0-2026-07-26;syndication=syndication-v1.0-2026-07-26;version=version-link-v1.0-2026-07-26;clusters=cluster-validation-v1.0-2026-07-26;canonical=canonical-v1.0-2026-07-26` (sha256 per file in the manifest)
* records: 1546 (one per Phase 4 article; reconciled)
* relationship statuses: {'archive_version': 3, 'canonical_article': 4, 'non_duplicate_independent_article': 1538, 'updated_version': 1}
* downstream usage: {'retain_as_evidence_only': 4, 'use_as_canonical_input': 1542}
* review queue: 0 rows

## Coverage (do not mistake for the final corpus)

Included: Stage A-L collection plus the completed portion of the Stage M windowed re-sweep, processed through Phase 4 normalisation and Phase 5 Steps 1-7. NOT included: the remaining Stage M queries (~600) still to run. This layer therefore freezes the duplicate-resolution STATE of the current snapshot, not the dissertation corpus.

## Incremental update procedure (v2 and later)

1. new Stage M articles land as raw records and pass Phase 4 into a v2 normalised layer (v1 untouched);
2. Phase 5 Steps 1-7 rerun over the enlarged corpus - content-hash-derived family ids keep unchanged families stable, and only families whose membership actually changes get new ids;
3. the rebuilt mapping freezes as duplicate_mapping_layer_v2_provisional ALONGSIDE this file; the freeze guard refuses any in-place rewrite of v1;
4. downstream work pins the layer version it consumed.

Relationship types remain separate columns throughout; pairwise evidence lives in the Step 1-7 outputs referenced by family id. No article was deleted, no record merged, and Phase 6 (LLM extraction) was not started.
