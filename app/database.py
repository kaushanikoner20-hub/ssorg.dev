"""Stage 3: the SQLite data-access layer for ssorg.dev.

All database work happens in this file. The database is a single file
(default: data/ssorg.db) created automatically the first time it is used.

How it stays safe and simple:
- Every function opens its own short-lived connection and closes it again,
  so connections are never shared between Streamlit reruns or threads.
- Every query uses "?" placeholders. User text is never pasted into SQL.
- Changes are committed together, or rolled back if something fails.
- Problems are reported as DatabaseError with a plain message.
  Raw SQLite errors (and their stack traces) are not shown to users.

Search (Stage 4) is also here, because it is SQL: search_screenshot_rows.

Screenshot records are returned as plain dictionaries. The three list fields
are stored as JSON text in the database and come back as real Python lists
under the names important_dates, named_entities and useful_search_terms.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from app import config

# Possible values of the processing_status column
STATUS_PENDING = "pending"        # saved, analysis not finished yet
STATUS_COMPLETE = "complete"      # OCR and AI analysis both worked
STATUS_NO_TEXT = "no_text"        # image kept, no readable text found
STATUS_OCR_FAILED = "ocr_failed"  # image kept, OCR could not run
STATUS_AI_FAILED = "ai_failed"    # image and OCR text kept, AI analysis failed
PROCESSING_STATUSES = (
    STATUS_PENDING, STATUS_COMPLETE, STATUS_NO_TEXT, STATUS_OCR_FAILED, STATUS_AI_FAILED,
)

SCHEMA_VERSION = 1


class DatabaseError(Exception):
    """Something went wrong with the library database. The message is safe to show."""


class DuplicateScreenshotError(DatabaseError):
    """A screenshot with the same file hash is already in the library."""


def _status_list_sql() -> str:
    # Built only from our own constants above, never from user input.
    return ", ".join(f"'{status}'" for status in PROCESSING_STATUSES)


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS screenshots (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename         TEXT    NOT NULL,
    stored_filename           TEXT    NOT NULL UNIQUE,
    file_hash                 TEXT    NOT NULL UNIQUE,
    file_size                 INTEGER NOT NULL CHECK (file_size >= 0),
    mime_type                 TEXT    NOT NULL,
    created_at                TEXT    NOT NULL,
    ocr_text                  TEXT    NOT NULL DEFAULT '',
    category                  TEXT,
    short_summary             TEXT,
    important_dates_json      TEXT    NOT NULL DEFAULT '[]',
    named_entities_json       TEXT    NOT NULL DEFAULT '[]',
    useful_search_terms_json  TEXT    NOT NULL DEFAULT '[]',
    confidence                TEXT,
    processing_status         TEXT    NOT NULL DEFAULT '{STATUS_PENDING}'
                              CHECK (processing_status IN ({_status_list_sql()})),
    processing_error          TEXT
)
"""

CREATE_INDEX_SQL = (
    # file_hash already has an index because it is UNIQUE; the lookups below are
    # for the library page and the dashboard.
    "CREATE INDEX IF NOT EXISTS idx_screenshots_created_at ON screenshots (created_at)",
    "CREATE INDEX IF NOT EXISTS idx_screenshots_category ON screenshots (category)",
    "CREATE INDEX IF NOT EXISTS idx_screenshots_status ON screenshots (processing_status)",
)


# ----- Connections -----
def _resolve_path(db_path: str | Path | None) -> Path:
    """Use the path we were given, or the one from config.py (read at call time)."""
    return Path(db_path) if db_path else Path(config.DATABASE_PATH)


@contextmanager
def _connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on failure, always close."""
    path = _resolve_path(db_path)
    connection = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute(CREATE_TABLE_SQL)
        for statement in CREATE_INDEX_SQL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")  # fixed integer, not user input
        yield connection
        connection.commit()
    except sqlite3.Error as error:
        if connection is not None:
            connection.rollback()
        raise DatabaseError("The screenshot library could not be read or written.") from error
    except OSError as error:  # for example the data folder cannot be created
        if connection is not None:
            connection.rollback()
        raise DatabaseError("The data folder for the screenshot library could not be used.") from error
    except Exception:
        # Not a SQLite problem (for example our own DuplicateScreenshotError):
        # still undo any half-finished changes, then pass the error on.
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


def initialize_database(db_path: str | Path | None = None) -> Path:
    """Create the data folder, database file, table and indexes if they are missing.

    Safe to call as often as you like. Returns the database path.
    """
    with _connect(db_path):
        pass
    return _resolve_path(db_path)


# ----- JSON list helpers -----
def _to_json_list(values: list[str] | None) -> str:
    """Turn a list of strings into JSON text for storage."""
    return json.dumps([str(value) for value in (values or [])], ensure_ascii=False)


def _parse_json_list(text: str | None) -> list[str]:
    """Read a stored JSON list. Anything unexpected becomes an empty list."""
    try:
        data = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a database row to a dictionary with real lists for the JSON fields."""
    record = dict(row)
    record["important_dates"] = _parse_json_list(record.pop("important_dates_json", None))
    record["named_entities"] = _parse_json_list(record.pop("named_entities_json", None))
    record["useful_search_terms"] = _parse_json_list(record.pop("useful_search_terms_json", None))
    return record


# ----- Create -----
def add_screenshot(
    original_filename: str,
    stored_filename: str,
    file_hash: str,
    file_size: int,
    mime_type: str,
    ocr_text: str = "",
    category: str | None = None,
    short_summary: str | None = None,
    important_dates: list[str] | None = None,
    named_entities: list[str] | None = None,
    useful_search_terms: list[str] | None = None,
    confidence: str | None = None,
    processing_status: str = STATUS_PENDING,
    processing_error: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Insert a new screenshot record and return its id.

    Raises DuplicateScreenshotError if a record with the same file_hash exists.
    """
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO screenshots (
                    original_filename, stored_filename, file_hash, file_size, mime_type,
                    created_at, ocr_text, category, short_summary,
                    important_dates_json, named_entities_json, useful_search_terms_json,
                    confidence, processing_status, processing_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    original_filename, stored_filename, file_hash, file_size, mime_type,
                    created_at, ocr_text, category, short_summary,
                    _to_json_list(important_dates), _to_json_list(named_entities),
                    _to_json_list(useful_search_terms),
                    confidence, processing_status, processing_error,
                ),
            )
        except sqlite3.IntegrityError as error:
            if "file_hash" in str(error):
                raise DuplicateScreenshotError("This screenshot is already in your library.") from error
            raise DatabaseError("The screenshot could not be added to the library.") from error
        return int(cursor.lastrowid)


# ----- Read -----
def get_screenshot_by_id(screenshot_id: int, db_path: str | Path | None = None) -> dict | None:
    """Return one record, or None if there is no screenshot with this id."""
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_screenshot_by_hash(file_hash: str, db_path: str | Path | None = None) -> dict | None:
    """Return the record with this SHA-256 hash, or None. Used for duplicate detection."""
    with _connect(db_path) as connection:
        row = connection.execute("SELECT * FROM screenshots WHERE file_hash = ?", (file_hash,)).fetchone()
    return _row_to_dict(row) if row else None


def get_all_screenshots(
    limit: int | None = None, offset: int = 0, db_path: str | Path | None = None
) -> list[dict]:
    """Return records, newest first. `limit=None` means no limit."""
    sql_limit = -1 if limit is None else int(limit)  # SQLite: LIMIT -1 means "no limit"
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM screenshots ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (sql_limit, int(offset)),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_screenshot_count(db_path: str | Path | None = None) -> int:
    """How many screenshots are in the library."""
    with _connect(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0])


def get_category_counts(db_path: str | Path | None = None) -> dict[str, int]:
    """Return {category: how many screenshots}. Screenshots without a category are skipped."""
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT category, COUNT(*) AS total FROM screenshots
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category ORDER BY total DESC, category ASC
            """
        ).fetchall()
    return {row["category"]: int(row["total"]) for row in rows}


def get_recent_screenshot_count(days: int = 7, db_path: str | Path | None = None) -> int:
    """How many screenshots were imported in the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM screenshots WHERE created_at >= ?", (cutoff,)).fetchone()
    return int(row[0])


# ----- Update -----
def update_screenshot_processing(
    screenshot_id: int,
    processing_status: str,
    ocr_text: str = "",
    category: str | None = None,
    short_summary: str | None = None,
    important_dates: list[str] | None = None,
    named_entities: list[str] | None = None,
    useful_search_terms: list[str] | None = None,
    confidence: str | None = None,
    processing_error: str | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Save OCR and AI results for a screenshot. Returns False if the id does not exist."""
    with _connect(db_path) as connection:
        try:
            cursor = connection.execute(
                """
                UPDATE screenshots SET
                    ocr_text = ?, category = ?, short_summary = ?,
                    important_dates_json = ?, named_entities_json = ?, useful_search_terms_json = ?,
                    confidence = ?, processing_status = ?, processing_error = ?
                WHERE id = ?
                """,
                (
                    ocr_text, category, short_summary,
                    _to_json_list(important_dates), _to_json_list(named_entities),
                    _to_json_list(useful_search_terms),
                    confidence, processing_status, processing_error, screenshot_id,
                ),
            )
        except sqlite3.IntegrityError as error:  # for example an invalid status value
            raise DatabaseError("The processing results could not be saved.") from error
        return cursor.rowcount > 0


# ----- Delete -----
def delete_screenshot_record(screenshot_id: int, db_path: str | Path | None = None) -> bool:
    """Delete one database record. Returns False if the id did not exist.

    This only touches the database. Removing the image file is done by
    processor.delete_screenshot, which uses the checks in storage.py.
    """
    with _connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM screenshots WHERE id = ?", (screenshot_id,))
        return cursor.rowcount > 0


# ----- Search (Stage 4) -----
# Which columns are searched, and how much a match in each one counts toward the
# relevance score. These are fixed names written in this file. User text is
# NEVER added to the SQL text; it only travels as "?" parameters.
SEARCH_FIELD_WEIGHTS = (
    ("category", 4),
    ("useful_search_terms_json", 4),
    ("named_entities_json", 4),
    ("short_summary", 3),
    ("original_filename", 3),
    ("important_dates_json", 2),
    ("ocr_text", 1),
)

# Only these sort orders exist; an unknown value falls back to relevance.
SORT_ORDERS = {
    "relevance": "relevance_score DESC, created_at DESC, id DESC",
    "newest": "created_at DESC, id DESC",
    "oldest": "created_at ASC, id ASC",
    "category": "category IS NULL, category COLLATE NOCASE ASC, created_at DESC, id DESC",
}


def escape_like(text: str) -> str:
    """Make text safe for a LIKE pattern, so % and _ are matched literally.

    We use the backslash as the escape character (ESCAPE '\\' in the SQL below).
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_screenshot_rows(
    terms: list[str] | tuple[str, ...] = (),
    match_all: bool = True,
    category: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    sort: str = "relevance",
    limit: int = 20,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> tuple[list[dict], int]:
    """Find screenshots whose text fields contain the given terms.

    - Each term may appear in ANY searchable field (case-insensitive for ASCII).
    - match_all=True: a screenshot must contain every term. False: any term is enough.
    - category: exact category name. created_from / created_to: UTC ISO timestamps
      (from is inclusive, to is exclusive).
    - Returns (records for this page, total number of matches). Each record has a
      "relevance_score". One screenshot is one row, so there are never duplicates.
    """
    terms = [term for term in (terms or []) if term]
    patterns = [f"%{escape_like(term)}%" for term in terms]

    # Score: add up the weight of every (term, field) pair that matches.
    score_parts: list[str] = []
    score_params: list[str] = []
    for pattern in patterns:
        for field, weight in SEARCH_FIELD_WEIGHTS:
            score_parts.append(f"CASE WHEN {field} LIKE ? ESCAPE '\\' THEN {int(weight)} ELSE 0 END")
            score_params.append(pattern)
    score_sql = " + ".join(score_parts) if score_parts else "0"

    # Filter: each term must be found in at least one field.
    where_params: list = []
    term_clauses = []
    for pattern in patterns:
        any_field = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field, _ in SEARCH_FIELD_WEIGHTS)
        term_clauses.append(f"({any_field})")
        where_params.extend([pattern] * len(SEARCH_FIELD_WEIGHTS))
    conditions = []
    if term_clauses:
        conditions.append("(" + (" AND " if match_all else " OR ").join(term_clauses) + ")")
    if category:
        conditions.append("category = ?")
        where_params.append(category)
    if created_from:
        conditions.append("created_at >= ?")
        where_params.append(created_from)
    if created_to:
        conditions.append("created_at < ?")
        where_params.append(created_to)
    where_sql = " AND ".join(conditions) if conditions else "1 = 1"

    order_sql = SORT_ORDERS.get(sort, SORT_ORDERS["relevance"])
    page_size = max(1, min(int(limit), config.SEARCH_MAX_LIMIT))
    page_offset = max(0, int(offset))

    with _connect(db_path) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM screenshots WHERE {where_sql}", where_params
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT *, ({score_sql}) AS relevance_score FROM screenshots "
            f"WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            score_params + where_params + [page_size, page_offset],
        ).fetchall()
    return [_row_to_dict(row) for row in rows], int(total)