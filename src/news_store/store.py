"""The store's public interface.

Every method here exists so that a caller cannot do the wrong thing by
accident. There is no ``update_extraction``, because Prompt 2 forbids
overwriting the model's output and the way to guarantee that is to provide no
way to do it. There is no ``set_value``, because a value is either what the
model said or what a reviewer said instead, and those are recorded
differently. Reading a value always returns its provenance alongside it, so
model output cannot be presented as human-reviewed simply by forgetting to
check.

The store holds no credentials of any kind. Prompt 2 forbids an API key from
reaching the database, the logs or an export; the simplest way to comply is
for no method to accept one.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .schema import (
    PROVENANCE_AI,
    PROVENANCE_REVIEWED,
    REVIEW_STATUSES,
    connect,
)

# Field names that must never be written into the store, whatever the caller
# passes. Checked rather than trusted: a key that reaches an audit trail
# cannot be un-leaked, and this is cheap.
#
# What this does NOT do, stated plainly so nobody relies on more than it
# gives: it guards field *names*, not values. `field="api_key"` is refused;
# `field="headline", value="sk-..."` is not, and cannot be without refusing
# article text that happens to contain such a string. The real protection is
# structural - no method here accepts a credential parameter, the extraction
# client never passes one, and the API key lives in process memory only. This
# is the last line, not the first.
FORBIDDEN_FIELDS = frozenset({
    "api_key", "openai_api_key", "anthropic_api_key", "authorization",
    "secret", "token", "password", "bearer",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_text(value: object) -> str | None:
    """Store everything as text, JSON-encoding anything structured.

    A single column type keeps the resolved view simple, and JSON keeps a list
    of ward ids or a nested evidence block readable and reversible instead of
    being flattened into something lossy.
    """

    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return json.dumps(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class ResolvedValue:
    """A value and where it came from.

    ``provenance`` is returned with every read because Prompt 2 requires that
    model-generated classifications are never presented as human-reviewed, and
    an interface that returns a bare value invites exactly that.
    """

    article_id: str
    record_type: str
    record_key: str
    field: str
    value: str | None
    provenance: str
    ai_value: str | None
    reviewed_value: str | None
    confidence: float | None
    evidence: str | None
    model: str | None
    correction_reason: str | None

    @property
    def is_reviewed(self) -> bool:
        return self.provenance == PROVENANCE_REVIEWED


class NewsStore:
    """A project's article store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.connection: sqlite3.Connection = connect(self.path)

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "NewsStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _log(self, action: str, article_id: str | None = None,
             detail: object = None) -> None:
        self.connection.execute(
            "INSERT INTO audit_log (happened_at, action, article_id, detail) "
            "VALUES (?, ?, ?, ?)",
            (_now(), action, article_id, _as_text(detail)),
        )

    # -- raw articles -----------------------------------------------------

    def add_raw_article(self, article: Mapping[str, object]) -> str:
        """Store an article exactly as it arrived.

        Re-adding the same ``article_id`` is a no-op rather than an overwrite.
        The raw table is the evidence the rest of the store points at; letting
        a second import silently replace it would break every reference to it.
        """

        article_id = str(article["article_id"])
        existing = self.connection.execute(
            "SELECT 1 FROM raw_article WHERE article_id = ?", (article_id,)
        ).fetchone()
        if existing:
            self._log("raw_article_already_present", article_id)
            return article_id

        self.connection.execute(
            "INSERT INTO raw_article (article_id, batch_id, source_id, publisher,"
            " headline, original_url, published_date, published_time,"
            " date_confidence, retrieval_status, text_sha256, imported_at,"
            " original_payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                article_id,
                _as_text(article.get("batch_id")),
                _as_text(article.get("source_id")),
                _as_text(article.get("publisher")),
                _as_text(article.get("headline")),
                _as_text(article.get("original_url")),
                _as_text(article.get("published_date")),
                _as_text(article.get("published_time")),
                _as_text(article.get("date_confidence")),
                _as_text(article.get("retrieval_status")),
                _as_text(article.get("text_sha256")),
                _now(),
                _as_text(dict(article)),
            ),
        )
        self._log("raw_article_added", article_id)
        self.connection.commit()
        return article_id

    def add_cleaned_text(self, article_id: str, cleaned_text: str, *,
                         method: str, version: str,
                         word_count: int | None = None) -> None:
        """Store cleaned text beside the original, never over it."""

        self.connection.execute(
            "INSERT OR REPLACE INTO cleaned_article (article_id, cleaned_text,"
            " word_count, cleaning_method, cleaning_version, cleaned_at)"
            " VALUES (?,?,?,?,?,?)",
            (article_id, cleaned_text,
             word_count if word_count is not None else len(cleaned_text.split()),
             method, version, _now()),
        )
        self._log("cleaned_text_stored", article_id, {"method": method})
        self.connection.commit()

    # -- extraction -------------------------------------------------------

    def record_extraction(
        self,
        article_id: str,
        *,
        record_type: str,
        field: str,
        value: object,
        model: str,
        prompt_version: str,
        schema_version: str,
        record_key: str = "",
        confidence: float | None = None,
        evidence: str | None = None,
        evidence_page: int | None = None,
    ) -> int:
        """Record one thing the model said. There is no way to change it later.

        A correction is a separate row in a separate table, so this method
        being insert-only is what makes "do not overwrite or destroy the
        original AI output" structurally true.
        """

        if field.lower() in FORBIDDEN_FIELDS:
            raise ValueError(
                f"Refusing to store a field named {field!r}: credentials must "
                "never reach the store, the logs or an export."
            )
        cursor = self.connection.execute(
            "INSERT INTO extraction_value (article_id, record_type, record_key,"
            " field, value, confidence, evidence, evidence_page, model,"
            " prompt_version, schema_version, extracted_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (article_id, record_type, record_key, field, _as_text(value),
             confidence, evidence, evidence_page, model, prompt_version,
             schema_version, _now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    # -- review -----------------------------------------------------------

    def record_review(
        self,
        article_id: str,
        *,
        status: str,
        reviewer: str | None = None,
        note: str | None = None,
        corrections: Sequence[Mapping[str, object]] = (),
    ) -> int:
        """Record one review of one article, with any fields it changed.

        ``corrections`` entries need ``record_type``, ``field`` and
        ``final_value``; ``record_key`` and ``reason`` are optional. The AI
        value each one replaces is looked up here rather than supplied by the
        caller, so a correction cannot record a value the model never gave.

        A review that changed nothing writes no corrections and is recorded as
        ``reviewed_unchanged`` - which is why the event exists separately from
        the corrections.
        """

        if status not in REVIEW_STATUSES:
            raise ValueError(
                f"Unknown review status {status!r}. Prompt 2's statuses are "
                f"{list(REVIEW_STATUSES)}."
            )
        if corrections and status != "reviewed_and_corrected":
            raise ValueError(
                f"Status {status!r} was given with {len(corrections)} "
                "correction(s). A review that changed something is "
                "'reviewed_and_corrected'; recording it otherwise would hide "
                "the change from the status filter."
            )

        cursor = self.connection.execute(
            "INSERT INTO review_event (article_id, status, reviewer, note,"
            " reviewed_at) VALUES (?,?,?,?,?)",
            (article_id, status, reviewer, note, _now()),
        )
        event_id = int(cursor.lastrowid)

        for correction in corrections:
            record_type = str(correction["record_type"])
            record_key = str(correction.get("record_key", ""))
            field = str(correction["field"])
            # The AI value is read from the store, not taken on trust.
            row = self.connection.execute(
                "SELECT value FROM extraction_value WHERE article_id=? AND"
                " record_type=? AND record_key=? AND field=?"
                " ORDER BY extraction_id DESC LIMIT 1",
                (article_id, record_type, record_key, field),
            ).fetchone()
            self.connection.execute(
                "INSERT INTO correction (event_id, article_id, record_type,"
                " record_key, field, ai_value, final_value, reason, corrected_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (event_id, article_id, record_type, record_key, field,
                 row["value"] if row else None,
                 _as_text(correction.get("final_value")),
                 _as_text(correction.get("reason")), _now()),
            )

        self._log("review_recorded", article_id,
                  {"status": status, "corrections": len(corrections)})
        self.connection.commit()
        return event_id

    def review_status(self, article_id: str) -> str:
        """The article's current review status.

        The latest event wins. An article nobody has looked at is
        ``not_reviewed`` - Prompt 2's default, and distinct from an article
        someone looked at and left alone.
        """

        row = self.connection.execute(
            "SELECT status FROM review_event WHERE article_id = ?"
            " ORDER BY event_id DESC LIMIT 1", (article_id,)
        ).fetchone()
        return row["status"] if row else "not_reviewed"

    def correction_history(self, article_id: str) -> list[dict]:
        """Every correction ever made to this article, oldest first.

        Including superseded ones. A field corrected twice shows both, which
        is the change history the brief asks to be retained.
        """

        rows = self.connection.execute(
            "SELECT c.*, r.reviewer, r.note AS review_note, r.status"
            " FROM correction AS c JOIN review_event AS r"
            " ON c.event_id = r.event_id WHERE c.article_id = ?"
            " ORDER BY c.correction_id", (article_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # -- reading ----------------------------------------------------------

    def resolve(self, article_id: str, record_type: str, field: str,
                record_key: str = "") -> ResolvedValue | None:
        """The value to use, and whether a human stood behind it."""

        row = self.connection.execute(
            "SELECT * FROM resolved_value WHERE article_id=? AND record_type=?"
            " AND record_key=? AND field=?",
            (article_id, record_type, record_key, field),
        ).fetchone()
        if row is None:
            return None
        return ResolvedValue(
            article_id=row["article_id"], record_type=row["record_type"],
            record_key=row["record_key"], field=row["field"],
            value=row["value_in_force"], provenance=row["provenance"],
            ai_value=row["ai_value"], reviewed_value=row["reviewed_value"],
            confidence=row["confidence"], evidence=row["evidence"],
            model=row["model"], correction_reason=row["correction_reason"],
        )

    def resolved_for_article(self, article_id: str) -> list[ResolvedValue]:
        """Every resolved field for one article, for the review screen."""

        rows = self.connection.execute(
            "SELECT * FROM resolved_value WHERE article_id = ?"
            " ORDER BY record_type, record_key, field", (article_id,)
        ).fetchall()
        return [
            ResolvedValue(
                article_id=r["article_id"], record_type=r["record_type"],
                record_key=r["record_key"], field=r["field"],
                value=r["value_in_force"], provenance=r["provenance"],
                ai_value=r["ai_value"], reviewed_value=r["reviewed_value"],
                confidence=r["confidence"], evidence=r["evidence"],
                model=r["model"], correction_reason=r["correction_reason"],
            )
            for r in rows
        ]

    # -- dashboard --------------------------------------------------------

    def review_dashboard(self, *, low_confidence: float = 0.5) -> dict:
        """The counts Prompt 2 asks the review dashboard to show."""

        def one(sql: str, *params) -> int:
            return int(self.connection.execute(sql, params).fetchone()[0])

        statuses = {
            status: one(
                "SELECT COUNT(*) FROM (SELECT article_id, status,"
                " ROW_NUMBER() OVER (PARTITION BY article_id ORDER BY event_id DESC)"
                " AS rn FROM review_event) WHERE rn = 1 AND status = ?", status)
            for status in REVIEW_STATUSES if status != "not_reviewed"
        }
        total = one("SELECT COUNT(*) FROM raw_article")
        reviewed = one("SELECT COUNT(DISTINCT article_id) FROM review_event")
        statuses["not_reviewed"] = total - reviewed

        return {
            "total_articles": total,
            "articles_with_an_extraction": one(
                "SELECT COUNT(DISTINCT article_id) FROM extraction_value"),
            "articles_reviewed": reviewed,
            "by_review_status": statuses,
            "articles_with_a_low_confidence_field": one(
                "SELECT COUNT(DISTINCT article_id) FROM extraction_value"
                " WHERE confidence IS NOT NULL AND confidence < ?", low_confidence),
            "corrections_made": one("SELECT COUNT(*) FROM correction"),
            "fields_currently_human_reviewed": one(
                "SELECT COUNT(*) FROM resolved_value WHERE provenance = ?",
                PROVENANCE_REVIEWED),
            "fields_still_model_only": one(
                "SELECT COUNT(*) FROM resolved_value WHERE provenance = ?",
                PROVENANCE_AI),
            "articles_excluded_by_window": one(
                "SELECT COUNT(DISTINCT article_id) FROM window_assignment"
                " WHERE included = 0"),
            "duplicate_groups": one(
                "SELECT COUNT(DISTINCT group_id) FROM duplicate_group"),
        }

    # -- window assignment and provenance ---------------------------------

    def record_window_assignment(self, article_id: str, election_id: str,
                                 assignment: Mapping[str, object]) -> None:
        """Store where an article falls for one election under one scheme.

        Keyed by scheme as well as election, because the brief contains three
        incompatible window definitions and an assignment that does not say
        which one produced it cannot be checked.
        """

        self.connection.execute(
            "INSERT OR REPLACE INTO window_assignment (article_id, election_id,"
            " window_scheme, days_before, window, cumulative, included,"
            " exclusion_reason, assigned_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (article_id, election_id,
             str(assignment["window_scheme"]),
             assignment.get("days_before_polling"),
             assignment.get("window"),
             _as_text(assignment.get("cumulative_windows")),
             1 if assignment.get("included_in_influence_features") else 0,
             assignment.get("exclusion_reason"), _now()),
        )
        self.connection.commit()

    def record_feature_provenance(self, feature_key: str,
                                  article_ids: Sequence[str],
                                  weights: Mapping[str, float] | None = None) -> None:
        """Record which articles a computed feature rests on."""

        weights = weights or {}
        self.connection.executemany(
            "INSERT OR REPLACE INTO feature_provenance (feature_key, article_id,"
            " weight) VALUES (?,?,?)",
            [(feature_key, a, weights.get(a)) for a in article_ids],
        )
        self.connection.commit()

    def articles_behind(self, feature_key: str) -> list[str]:
        """Trace one feature back to its articles."""

        return [
            row["article_id"] for row in self.connection.execute(
                "SELECT article_id FROM feature_provenance WHERE feature_key = ?"
                " ORDER BY article_id", (feature_key,))
        ]

    # -- export -----------------------------------------------------------

    def export_rows(self) -> list[dict]:
        """Every resolved field, with both values, for the workbook export.

        Prompt 2: "For exports, include both AI Value and Final Value." Both
        columns are always present, and ``provenance`` says which is in force,
        so a reader never has to infer whether a human saw it.
        """

        return [dict(row) for row in self.connection.execute(
            "SELECT article_id, record_type, record_key, field,"
            " ai_value AS 'AI Value', reviewed_value AS 'Reviewed Value',"
            " value_in_force AS 'Final Value', provenance, confidence,"
            " model, correction_reason, corrected_at"
            " FROM resolved_value ORDER BY article_id, record_type, field")]
