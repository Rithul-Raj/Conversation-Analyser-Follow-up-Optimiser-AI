"""
MongoDB persistence layer for conversation history.

Collections:
  conversations — stores every analyzed conversation with its result.

Design note:
  All functions use pymongo (sync driver).
  Connection URI is read from the MONGO_URI environment variable.
  Default URI: mongodb://localhost:27017   Database: followup_ai

  Drop-in replacement for database.py — all callers in main.py stay the same.
  Switch the imports in main.py from services.database to services.mongo_database
  to activate MongoDB instead of SQLite.
"""

import os
from datetime import datetime, timezone

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from services.utils import normalize_date_input, normalize_time_filter

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
_MONGO_URI    = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_DB_NAME      = os.getenv("MONGO_DB_NAME", "followup_ai")
_COLLECTION   = "conversations"

_client: MongoClient | None = None


def _get_collection():
    """Return the pymongo Collection, creating the client once."""
    global _client
    if _client is None:
        _client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client[_DB_NAME][_COLLECTION]


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init_db() -> None:
    """
    Create indexes if they do not exist. Call once at startup.
    MongoDB creates the collection automatically on first insert.
    """
    col = _get_collection()
    col.create_index([("lead_id", ASCENDING)], name="idx_lead_id")
    col.create_index([("created_at", DESCENDING)], name="idx_created_at")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def save_conversation(
    lead_id:           str,
    bde_id:            str,
    conversation_text: str,
    analysis:          dict,
) -> str:
    """
    Persist a new conversation + its AI analysis result.

    Args:
        lead_id:           Unique identifier for the lead.
        bde_id:            Employee ID of the BDE who handled the call.
        conversation_text: The raw conversation text analysed.
        analysis:          The validated LLMAnalysisOutput as a dict.

    Returns:
        The string representation of the MongoDB _id (ObjectId) of the saved document.
    """
    doc = {
        "lead_id":           lead_id,
        "bde_id":            bde_id,
        "conversation_text": conversation_text,
        "analysis":          analysis,
        "created_at":        datetime.now(timezone.utc).isoformat(),
    }
    result = _get_collection().insert_one(doc)
    return str(result.inserted_id)


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
    col   = _get_collection()
    sort  = DESCENDING if newest_first else ASCENDING
    rows  = col.find(
        {"lead_id": lead_id},
        sort=[("created_at", sort)],
        limit=limit,
    )

    result = []
    for doc in rows:
        result.append({
            "id":                str(doc["_id"]),
            "lead_id":           doc["lead_id"],
            "bde_id":            doc["bde_id"],
            "conversation_text": doc["conversation_text"],
            "analysis":          doc["analysis"],
            "created_at":        doc["created_at"],
        })

    # When fetching oldest→newest for AI context with ASCENDING sort,
    # the result is already in the right order. No reversal needed.
    return result


def get_all_leads() -> list[dict]:
    """
    Return a summary of all unique leads: lead_id, total interactions,
    and timestamp of the most recent conversation.
    """
    col = _get_collection()
    pipeline = [
        {
            "$group": {
                "_id":               "$lead_id",
                "total_interactions": {"$sum": 1},
                "last_interaction":  {"$max": "$created_at"},
            }
        },
        {"$sort": {"last_interaction": -1}},
        {"$project": {"_id": 0, "lead_id": "$_id", "total_interactions": 1, "last_interaction": 1}},
    ]
    return list(col.aggregate(pipeline))


def _time_matches(needle: str, stored: str) -> bool:
    """
    Check whether a normalised time needle matches a stored time string.

    Uses exact equality for single times and checks both ends of a range,
    avoiding the substring collision where '1:00 pm' falsely matches '11:00 pm'.
    """
    stored_lc = stored.lower().strip()
    if stored_lc == needle:
        return True
    if " - " in stored_lc:
        return needle in [p.strip() for p in stored_lc.split(" - ")]
    return False


def get_conversations_by_date(date_str: str, time_str: str | None = None) -> list[dict]:
    """
    Find all leads whose LATEST scheduled_followup_date matches date_str.

    Key design decisions:
      - Only the most recent conversation per lead is checked.
      - date_str is normalised to a zero-padded day.
      - Time matching uses exact equality (not substring).

    Returns a list of matching records (lead_id, bde_id, analysis, created_at).
    """
    needle_date = normalize_date_input(date_str).lower()
    needle_time = normalize_time_filter(time_str) if time_str else None

    col = _get_collection()
    pipeline = [
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id":        "$lead_id",
                "lead_id":    {"$first": "$lead_id"},
                "bde_id":     {"$first": "$bde_id"},
                "analysis":   {"$first": "$analysis"},
                "created_at": {"$first": "$created_at"},
            }
        },
    ]
    rows = list(col.aggregate(pipeline))

    results = []
    for row in rows:
        analysis    = row["analysis"]
        stored_date = normalize_date_input(
            analysis.get("scheduled_followup_date") or ""
        ).lower()
        stored_time = analysis.get("scheduled_followup_time") or ""

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
    """Return the total number of stored conversations for a lead."""
    return _get_collection().count_documents({"lead_id": lead_id})


def get_conversation_by_id(conversation_id: str) -> dict | None:
    """Return a single conversation record by its MongoDB _id string, or None if not found."""
    from bson import ObjectId
    try:
        oid = ObjectId(conversation_id)
    except Exception:
        return None

    col = _get_collection()
    doc = col.find_one({"_id": oid})
    if doc is None:
        return None
    return {
        "id":                str(doc["_id"]),
        "lead_id":           doc["lead_id"],
        "bde_id":            doc["bde_id"],
        "conversation_text": doc["conversation_text"],
        "analysis":          doc["analysis"],
        "created_at":        doc["created_at"],
    }
