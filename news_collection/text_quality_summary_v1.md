# Text quality - Step 6 summary (v1)

* rules: `text-quality-v1.0-2026-07-27`
* articles assessed: **1546** (equals the Step 5 population; input body hash recorded per row - this step never edits text, so output hash == input hash)
* statuses: {'valid_full_text': 1539, 'review_required': 1, 'missing_body': 6}
* warning flags: {'possible_truncation': 295, 'step3:possible_mojibake_unrepaired': 1, 'duplicate_paragraphs': 18, 'step4:sentence_per_line': 9, 'step4:single_paragraph_wall': 1406, 'title_only_shape': 1, 'media_only_resolved': 6}
* review queue: 1 rows

Status rules and thresholds are documented in `src/normalisation/text_quality.py`.
