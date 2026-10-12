"""
Notification service — pure Python, zero AI, zero API cost.

Provides three search/filter operations over a list of ReminderEntry objects:

1. filter_by_date   — find entries matching a specific date (time optional)
2. get_daily_summary — return OVERDUE, TODAY, TOMORROW entries sorted by urgency
3. find_by_client   — search entries by client name or client_id (case-insensitive)

Design note:
    All functions accept an explicit list of entries rather than querying a
    database. This keeps the service stateless for now. When a database is
    added in the future, each function's body just changes to a DB query —
    the endpoint signatures stay the same.
"""

from datetime import datetime

from schemas.conversation_analysis import ReminderStatus
from services.reminder_service import compute_reminder
from services.utils import normalize_time_filter

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_DATE_FORMAT = "%d %b %Y"

_STATUS_ORDER = {
    ReminderStatus.OVERDUE:       0,
    ReminderStatus.TODAY:         1,
    ReminderStatus.TOMORROW:      2,
    ReminderStatus.THIS_WEEK:     3,
    ReminderStatus.UPCOMING:      4,
    ReminderStatus.NOT_SCHEDULED: 5,
}

_URGENT_STATUSES = {
    ReminderStatus.OVERDUE,
    ReminderStatus.TODAY,
    ReminderStatus.TOMORROW,
}


def _parse_date(date_str: str | None):
    """Parse a 'DD Mon YYYY' string into a date object, or return None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), _DATE_FORMAT).date()
    except ValueError:
        return None


def _dates_match(entry_date: str | None, search_date: str) -> bool:
    """Return True if both strings represent the same calendar date."""
    d1 = _parse_date(entry_date)
    d2 = _parse_date(search_date)
    return d1 is not None and d2 is not None and d1 == d2


def _time_matches(entry_time: str, search_time: str | None) -> bool:
    """
    Return True if search_time matches the entry_time.
    If search_time is None or 'Not specified', every entry matches.
    Uses exact equality (not substring) to prevent '1:00 pm' matching '11:00 pm'.
    """
    if not search_time or search_time.strip().lower() == "not specified":
        return True
    needle     = normalize_time_filter(search_time)
    stored_lc  = (entry_time or "").lower().strip()
    if stored_lc == needle:
        return True
    if " - " in stored_lc:
        return needle in [p.strip() for p in stored_lc.split(" - ")]
    return False


def _enrich(entry: dict) -> dict:
    """Attach a computed reminder block to an entry dict."""
    result = compute_reminder(
        entry.get("scheduled_followup_date"),
        entry.get("scheduled_followup_time", "Not specified"),
    )
    return {**entry, "reminder": result.to_dict()}


def _sort_key(enriched_entry: dict) -> int:
    status_str = enriched_entry.get("reminder", {}).get("status", "NOT_SCHEDULED")
    try:
        status = ReminderStatus(status_str)
    except ValueError:
        status = ReminderStatus.NOT_SCHEDULED
    return _STATUS_ORDER.get(status, 99)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_by_date(
    entries: list[dict],
    date_str: str,
    time_str: str | None = None,
) -> list[dict]:
    """
    Return all entries whose scheduled_followup_date matches date_str.
    Optionally narrow results to entries whose time contains time_str.
    Results are sorted by reminder urgency (OVERDUE first).
    """
    matched = []
    for entry in entries:
        if _dates_match(entry.get("scheduled_followup_date"), date_str):
            entry_time = entry.get("scheduled_followup_time", "Not specified")
            if _time_matches(entry_time, time_str):
                matched.append(_enrich(entry))
    matched.sort(key=_sort_key)
    return matched


def get_daily_summary(entries: list[dict]) -> list[dict]:
    """
    Return all entries whose reminder status is OVERDUE, TODAY, or TOMORROW,
    sorted by urgency (OVERDUE → TODAY → TOMORROW).
    """
    enriched = [_enrich(e) for e in entries]
    urgent = []
    for e in enriched:
        status_str = e.get("reminder", {}).get("status", "")
        try:
            if ReminderStatus(status_str) in _URGENT_STATUSES:
                urgent.append(e)
        except ValueError:
            pass
    urgent.sort(key=_sort_key)
    return urgent


def find_by_client(entries: list[dict], identifier: str) -> list[dict]:
    """
    Return all entries where identifier (case-insensitive) is a substring
    of client_name or client_id. Results are sorted by reminder urgency.
    """
    needle = identifier.strip().lower()
    matched = []
    for entry in entries:
        name = (entry.get("client_name") or "").lower()
        cid  = (entry.get("client_id")   or "").lower()
        if needle in name or needle in cid:
            matched.append(_enrich(entry))
    matched.sort(key=_sort_key)
    return matched
