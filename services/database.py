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
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
def get_lead_history(lead_id: str, limit: int = 5) -> list[dict]:
    """
    Return the most recent `limit` conversations for a lead, in
    chronological order (oldest first) so the AI gets proper context flow.

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

    # Reverse so oldest → newest (chronological context for the AI)
    result = []
    for row in reversed(rows):
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


def _normalize_time_filter(raw: str) -> str:
    """
    Standardise a user-typed time filter so it matches stored times.

    Handles the common mismatch where the user types "7 pm" but the
    stored value is "7:00 PM".

    Rules:
      "7 pm"   → "7:00 pm"     (adds :00 when minutes are omitted)
      "7PM"    → "7:00 pm"     (space-insensitive, lowercase)
      "7:30pm" → "7:30 pm"     (adds space before am/pm)
      "7:00 PM"→ "7:00 pm"     (already correct, just lowercased)
      "morning"→ "morning"     (vague words pass through unchanged)
    """
    t = raw.strip().lower()
    # Insert :00 when hour is given with no minutes, e.g. "7 pm" or "7pm"
    t = re.sub(r'^(\d{1,2})\s*(am|pm)$', r'\1:00 \2', t)
    # Ensure space between time digits and am/pm, e.g. "7:30pm" → "7:30 pm"
    t = re.sub(r'^(\d{1,2}:\d{2})\s*(am|pm)$', r'\1 \2', t)
    return t


def get_conversations_by_date(date_str: str, time_str: str | None = None) -> list[dict]:
    """
    Search all stored conversations whose AI-extracted scheduled_followup_date
    matches date_str (case-insensitive). Optionally narrow by time_str substring.

    Returns a list of matching records (lead_id, bde_id, analysis, created_at).
    This is used by the terminal CLI's 'Find by date' feature.
    """
    needle_date = date_str.strip().lower()
    needle_time = _normalize_time_filter(time_str) if time_str else None

    with _connect() as conn:
        rows = conn.execute(
            "SELECT lead_id, bde_id, analysis_json, created_at FROM conversations"
        ).fetchall()

    results = []
    for row in rows:
        analysis = json.loads(row["analysis_json"])
        followup_date = (analysis.get("scheduled_followup_date") or "").strip().lower()
        followup_time = (analysis.get("scheduled_followup_time") or "").lower()

        if followup_date == needle_date:
            if needle_time is None or needle_time in followup_time:
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

