"""
SQLite persistence layer for conversation history.

Tables:
  conversations — stores every analyzed conversation with its result.

Design note:
  All functions use plain sqlite3 (stdlib, zero new dependencies).
  The DB file lives at: conversation_ai/data/conversations.db

  When a proper database (PostgreSQL, etc.) is integrated in the future,
  only this file needs to change — all callers stay the same.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from services.utils import normalize_date_input, normalize_time_filter

# ---------------------------------------------------------------------------
# DB location
# ---------------------------------------------------------------------------
_DB_DIR  = Path(__file__).parent.parent / "data"
_DB_PATH = _DB_DIR / "conversations.db"


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create tables and indexes if they do not exist. Call once at startup."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id           TEXT    NOT NULL,
                bde_id            TEXT    NOT NULL,
                conversation_text TEXT    NOT NULL,
                analysis_json     TEXT    NOT NULL,
                created_at        TEXT    NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lead_id ON conversations (lead_id)"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def save_conversation(
    lead_id:           str,
    bde_id:            str,
    conversation_text: str,
    analysis:          dict,
) -> int:
    """
    Persist a new conversation + its AI analysis result.

    Args:
        lead_id:           Unique identifier for the lead.
        bde_id:            Employee ID of the BDE who handled the call.
        conversation_text: The raw conversation text analysed.
        analysis:          The validated LLMAnalysisOutput as a dict.

    Returns:
        The auto-generated integer ID of the saved row.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations
                (lead_id, bde_id, conversation_text, analysis_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, bde_id, conversation_text, json.dumps(analysis), created_at),
        )
        conn.commit()
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def get_lead_history(
    lead_id: str,
    limit: int = 5,
    newest_first: bool = False,
) -> list[dict]:
    """
    Return up to `limit` conversations for a lead.

    Args:
        lead_id:      Normalised lead identifier.
        limit:        Maximum number of conversations to return.
        newest_first: If True, return newest→oldest (for display).
                      If False (default), return oldest→newest (for AI context).

    Each item contains:
        id, lead_id, bde_id, conversation_text, analysis (dict), created_at
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, lead_id, bde_id, conversation_text, analysis_json, created_at
            FROM   conversations
            WHERE  lead_id = ?
            ORDER  BY created_at DESC
            LIMIT  ?
            """,
            (lead_id, limit),
        ).fetchall()

    # Default: reverse so oldest → newest (chronological context for the AI)
    ordered = list(reversed(rows)) if not newest_first else list(rows)
    result = []
    for row in ordered:
        result.append({
            "id":                row["id"],
            "lead_id":           row["lead_id"],
            "bde_id":            row["bde_id"],
            "conversation_text": row["conversation_text"],
            "analysis":          json.loads(row["analysis_json"]),
            "created_at":        row["created_at"],
        })
    return result


def get_all_leads() -> list[dict]:
    """
    Return a summary of all unique leads: lead_id, total interactions,
    and timestamp of the most recent conversation.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT   lead_id,
                     COUNT(*)       AS total_interactions,
                     MAX(created_at) AS last_interaction
            FROM     conversations
            GROUP BY lead_id
            ORDER BY last_interaction DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _time_matches(needle: str, stored: str) -> bool:
    """
    Check whether a normalised time needle matches a stored time string.

    Uses exact equality for single times and checks both ends of a range,
    avoiding the substring collision where '1:00 pm' falsely matches '11:00 pm'.

    Examples:
      _time_matches('7:00 pm', '7:00 PM')            → True
      _time_matches('1:00 pm', '11:00 PM')            → False  (was True with substring)
      _time_matches('2:00 pm', '2:00 PM - 4:00 PM')  → True   (range start)
      _time_matches('morning', 'Morning')             → True
    """
    stored_lc = stored.lower().strip()
    if stored_lc == needle:
        return True
    # Handle time ranges like "2:00 pm - 4:00 pm"
    if " - " in stored_lc:
        return needle in [p.strip() for p in stored_lc.split(" - ")]
    return False


def get_conversations_by_date(date_str: str, time_str: str | None = None) -> list[dict]:
    """
    Find all leads whose LATEST scheduled_followup_date matches date_str.

    Key design decisions:
      - Only the most recent conversation per lead is checked, so a lead
        that was rescheduled no longer appears under its old date.
      - date_str is normalised to a zero-padded day so '5 Sep 2026' matches
        the stored '05 Sep 2026'.
      - Time matching uses exact equality (not substring) to prevent '1:00 pm'
        from falsely matching '11:00 pm'.

    Returns a list of matching records (lead_id, bde_id, analysis, created_at).
    """
    needle_date = normalize_date_input(date_str).lower()
    needle_time = normalize_time_filter(time_str) if time_str else None

    with _connect() as conn:
        # Subquery: fetch only the most recent conversation per lead
        rows = conn.execute(
            """
            SELECT c.lead_id, c.bde_id, c.analysis_json, c.created_at
            FROM   conversations c
            INNER JOIN (
                SELECT lead_id, MAX(created_at) AS max_ts
                FROM   conversations
                GROUP  BY lead_id
            ) AS latest
              ON c.lead_id   = latest.lead_id
             AND c.created_at = latest.max_ts
            """
        ).fetchall()

    results = []
    for row in rows:
        analysis     = json.loads(row["analysis_json"])
        stored_date  = normalize_date_input(
            analysis.get("scheduled_followup_date") or ""
        ).lower()
        stored_time  = (analysis.get("scheduled_followup_time") or "")

        if stored_date == needle_date:
            if needle_time is None or _time_matches(needle_time, stored_time):
                results.append({
                    "lead_id":    row["lead_id"],
                    "bde_id":     row["bde_id"],
                    "analysis":   analysis,
                    "created_at": row["created_at"],
                })
    return results


def get_lead_count(lead_id: str) -> int:
    """Return the total number of stored conversations for a lead (exact count)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE lead_id = ?",
            (lead_id,),
        ).fetchone()
    return row[0] if row else 0


def get_conversation_by_id(conversation_id: int) -> dict | None:
    """Return a single conversation record by its ID, or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, lead_id, bde_id, conversation_text, analysis_json, created_at
            FROM   conversations
            WHERE  id = ?
            """,
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id":                row["id"],
        "lead_id":           row["lead_id"],
        "bde_id":            row["bde_id"],
        "conversation_text": row["conversation_text"],
        "analysis":          json.loads(row["analysis_json"]),
        "created_at":        row["created_at"],
    }

