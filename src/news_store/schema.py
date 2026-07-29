"""The SQLite schema, and the one structural idea it is built around.

Prompt 2 asks for a structured local store, names SQLite as acceptable for a
local proof of concept, and requires "database migrations or a schema-version
table so later versions can upgrade projects safely". It also states the rule
this schema exists to make true:

    "Preserve: original AI value; final reviewed value; correction timestamp;
     reviewer note; correction reason. Do not overwrite or destroy the
     original AI output."

Corrections are inserted, never applied
---------------------------------------
The obvious design is a value column that a reviewer edits. It is also the one
design that cannot satisfy the rule: the moment an edit lands, the original is
gone, and "do not overwrite" becomes a convention somebody has to remember.

So nothing here is ever updated. ``extraction_value`` holds what the model
said and is written once. ``correction`` holds what a reviewer said instead,
as a new row carrying both the AI value it replaces and the reason. The value
to use is derived by looking for the most recent correction and falling back
to the extraction - which is exactly Prompt 2's rule, "use the final value in
aggregated feature calculations when a reviewed value exists, otherwise use
the AI value and mark it as unreviewed", expressed as a query rather than as
an instruction.

Change history then costs nothing: it is simply every correction row for that
field, in order. A reviewer who corrects a value twice leaves two rows, and
the first is still readable.

Why a review event is separate from a correction
------------------------------------------------
Prompt 2's review statuses include "reviewed unchanged", which a correction
table alone cannot express - a review that changed nothing writes no
correction, and would be indistinguishable from no review at all. A
``review_event`` is recorded whether or not anything changed, and corrections
hang off it. That also gives a reviewer, a timestamp and a note for a session
in which several fields were fixed at once, rather than repeating them per
field.

One generic shape, not five tables
----------------------------------
Prompt 2 lists article-ward links, entity mentions, issue mentions and frames
as separate record types, each reviewable. They have the same review needs, so
they share one addressing scheme: ``(article_id, record_type, record_key,
field)``. ``record_key`` is whatever identifies the specific link - a ward id,
a party name, an issue label - and is empty for fields that belong to the
article itself. Five near-identical tables would need five near-identical
review paths, and the fifth would be the one that gets it wrong.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Bumped whenever the DDL below changes. Stored in the database so an older
# file can be recognised and upgraded rather than silently misread.
SCHEMA_VERSION = 1

# Prompt 2's five review statuses, verbatim in meaning. "Reviewed unchanged"
# is the one that makes a separate review_event necessary.
REVIEW_STATUSES = (
    "not_reviewed",
    "reviewed_unchanged",
    "reviewed_and_corrected",
    "needs_review",
    "excluded",
)

# Where a value in use came from. Recorded on every read, because Prompt 2
# requires exports to show both and requires model output never to be
# presented as human-reviewed.
PROVENANCE_AI = "ai_unreviewed"
PROVENANCE_REVIEWED = "human_reviewed"

DDL = """
-- Schema version, so a project file built by an older version is recognised
-- rather than misread. One row per applied migration, never deleted.
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL,
    note        TEXT
);

-- Immutable record of an article as it arrived. Prompt 2: "Do not overwrite
-- the original article text with an LLM summary, cleaned text, corrected
-- text, extracted features or reviewed classifications." Cleaned text lives
-- in its own table for that reason.
CREATE TABLE IF NOT EXISTS raw_article (
    article_id      TEXT PRIMARY KEY,
    batch_id        TEXT,
    source_id       TEXT,
    publisher       TEXT,
    headline        TEXT,
    original_url    TEXT,
    published_date  TEXT,
    published_time  TEXT,
    date_confidence TEXT,
    retrieval_status TEXT,
    text_sha256     TEXT,
    imported_at     TEXT NOT NULL,
    original_payload TEXT          -- the source record verbatim, as JSON
);

-- Cleaned text, kept apart from the original so both survive.
CREATE TABLE IF NOT EXISTS cleaned_article (
    article_id      TEXT PRIMARY KEY REFERENCES raw_article(article_id),
    cleaned_text    TEXT,
    word_count      INTEGER,
    cleaning_method TEXT,
    cleaning_version TEXT,
    cleaned_at      TEXT NOT NULL
);

-- What the model said. Written once per (article, record, field) per
-- extraction version; never updated. A re-extraction under a new model or
-- prompt writes new rows and the old ones remain readable.
CREATE TABLE IF NOT EXISTS extraction_value (
    extraction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      TEXT NOT NULL REFERENCES raw_article(article_id),
    record_type     TEXT NOT NULL,   -- article | ward_link | entity_mention | issue | frame
    record_key      TEXT NOT NULL DEFAULT '',
    field           TEXT NOT NULL,
    value           TEXT,
    confidence      REAL,
    evidence        TEXT,
    evidence_page   INTEGER,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    extracted_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_extraction_target
    ON extraction_value (article_id, record_type, record_key, field);

-- One row per review action, whether or not anything changed. This is what
-- makes "reviewed unchanged" expressible.
CREATE TABLE IF NOT EXISTS review_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL REFERENCES raw_article(article_id),
    status      TEXT NOT NULL,
    reviewer    TEXT,
    note        TEXT,
    reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_article ON review_event (article_id);

-- One row per field a reviewer changed, carrying the AI value it replaces.
-- Append-only: correcting the same field twice leaves two rows and the first
-- stays readable, which is the change history Prompt 2 asks to be retained.
CREATE TABLE IF NOT EXISTS correction (
    correction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL REFERENCES review_event(event_id),
    article_id    TEXT NOT NULL REFERENCES raw_article(article_id),
    record_type   TEXT NOT NULL,
    record_key    TEXT NOT NULL DEFAULT '',
    field         TEXT NOT NULL,
    ai_value      TEXT,
    final_value   TEXT,
    reason        TEXT,
    corrected_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_correction_target
    ON correction (article_id, record_type, record_key, field, correction_id);

-- Duplicate groups. Every copy is retained; one member is canonical, and
-- aggregation counts one article per group by default.
CREATE TABLE IF NOT EXISTS duplicate_group (
    group_id     TEXT NOT NULL,
    article_id   TEXT NOT NULL REFERENCES raw_article(article_id),
    is_canonical INTEGER NOT NULL DEFAULT 0,
    method       TEXT,
    assigned_at  TEXT NOT NULL,
    PRIMARY KEY (group_id, article_id)
);

-- Where an article sits relative to one election. Kept per scheme, because
-- the three window definitions in the brief disagree and the assignment is
-- not meaningful without saying which one produced it.
CREATE TABLE IF NOT EXISTS window_assignment (
    article_id      TEXT NOT NULL REFERENCES raw_article(article_id),
    election_id     TEXT NOT NULL,
    window_scheme   TEXT NOT NULL,
    days_before     INTEGER,
    window          TEXT,
    cumulative      TEXT,           -- JSON list
    included        INTEGER NOT NULL,
    exclusion_reason TEXT,
    assigned_at     TEXT NOT NULL,
    PRIMARY KEY (article_id, election_id, window_scheme)
);

-- Which articles a computed feature rests on. Prompt 2: "Every generated
-- feature must be traceable back to its underlying article records."
CREATE TABLE IF NOT EXISTS feature_provenance (
    feature_key TEXT NOT NULL,      -- election|division|party|window|feature
    article_id  TEXT NOT NULL REFERENCES raw_article(article_id),
    weight      REAL,
    PRIMARY KEY (feature_key, article_id)
);

-- Append-only log of everything that touched the store, for the audit trail
-- Prompt 2 requires. Never contains a key, a secret or a request header.
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    happened_at TEXT NOT NULL,
    action     TEXT NOT NULL,
    article_id TEXT,
    detail     TEXT
);
"""

# The value in force for a field: the most recent correction if one exists,
# otherwise the extraction. Written as a view so every reader resolves it the
# same way and no caller can accidentally use the raw AI value where a
# correction exists.
RESOLVED_VIEW = f"""
CREATE VIEW IF NOT EXISTS resolved_value AS
SELECT
    e.article_id,
    e.record_type,
    e.record_key,
    e.field,
    e.value                                   AS ai_value,
    c.final_value                             AS reviewed_value,
    COALESCE(c.final_value, e.value)          AS value_in_force,
    CASE WHEN c.final_value IS NULL
         THEN '{PROVENANCE_AI}'
         ELSE '{PROVENANCE_REVIEWED}' END     AS provenance,
    e.confidence,
    e.evidence,
    e.model,
    c.reason                                  AS correction_reason,
    c.corrected_at
FROM extraction_value AS e
LEFT JOIN (
    -- The latest correction per target. MAX(correction_id) rather than
    -- MAX(corrected_at): two corrections in the same second would tie on the
    -- timestamp, and the insertion order is what "latest" means here.
    SELECT c1.*
    FROM correction AS c1
    JOIN (
        SELECT article_id, record_type, record_key, field,
               MAX(correction_id) AS latest
        FROM correction
        GROUP BY article_id, record_type, record_key, field
    ) AS newest
      ON c1.correction_id = newest.latest
) AS c
  ON  c.article_id  = e.article_id
  AND c.record_type = e.record_type
  AND c.record_key  = e.record_key
  AND c.field       = e.field;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a project store, creating and migrating it if necessary.

    Foreign keys are switched on explicitly: SQLite leaves them off by
    default, and a correction pointing at an article that does not exist is
    exactly the kind of silent breakage this store is meant to prevent.
    """

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrate(connection)
    return connection


def current_version(connection: sqlite3.Connection) -> int:
    """The highest applied schema version, or 0 for a fresh file."""

    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not tables:
        return 0
    row = connection.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0)


def migrate(connection: sqlite3.Connection) -> int:
    """Bring a store up to ``SCHEMA_VERSION``. Returns the version applied.

    Refuses to open a file written by a newer version rather than reading it
    with the wrong assumptions - a store from the future may have columns this
    code would ignore, and ignoring a column in an audit trail is worse than
    refusing to open it.
    """

    from datetime import datetime, timezone

    version = current_version(connection)
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"This store is schema version {version}; this code understands "
            f"{SCHEMA_VERSION}. Upgrade the code rather than opening it."
        )
    if version == SCHEMA_VERSION:
        return version

    connection.executescript(DDL)
    connection.executescript(RESOLVED_VIEW)
    connection.execute(
        "INSERT INTO schema_version (version, applied_at, note) VALUES (?, ?, ?)",
        (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "initial schema"),
    )
    connection.commit()
    return SCHEMA_VERSION
