# Canonical article selection - Step 7 report (v1 provisional)

* rules: `canonical-v1.0-2026-07-26`
* authoritative inputs: `layer=normalised-text-v1_provisional;clusters=cluster-validation-v1.0-2026-07-26;version=version-link-v1.0-2026-07-26;availability=version-link-v1.0-2026-07-26;syndication=syndication-v1.0-2026-07-26`
* families processed: 4 -> 3 canonical selected, 1 in review
* mapping rows: 1546 (one per Phase 4 article)
* status distribution: {'no_canonical_required_independent_articles': 1538, 'canonical_uncertain_manual_review': 2, 'canonical_selected': 6}
* downstream usage: {'llm_extraction_primary': 1541, 'held_pending_review': 2, 'duplicate_retained_not_counted': 3}
* temporal-leakage check: 0 violations (a canonical without confirmed pre-election availability is never chosen over a confirmed member; asserted at build time)

Ranking order: temporal validity, text usability, cleanliness, provenance, earlier-availability tiebreak, deterministic id order. Body length, publisher size, retrieval order and newest-version are deliberately not criteria. Archive captures are availability evidence, not automatic canonicals. All members remain mapped with their relationships; nothing was deleted or merged, and the final duplicate layer is not frozen here.
