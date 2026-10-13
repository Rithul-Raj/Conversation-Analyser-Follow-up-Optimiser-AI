"""
tests/test_reminder.py
-----------------------
Tests for reminder status computation logic.
Runs completely offline — no Gemini key or running server required.

Usage:
    pytest tests/test_reminder.py -v
    # or run directly:
    python tests/test_reminder.py
"""
import sys
sys.path.insert(0, ".")

from datetime import date, timedelta

from schemas.conversation_analysis import ReminderStatus
from services.reminder_service import compute_reminder


def _date_str(delta_days: int) -> str:
    """Return a date string (DD Mon YYYY) relative to today."""
    d = date.today() + timedelta(days=delta_days)
    return d.strftime("%d %b %Y")


CASES = [
    # (label,            scheduled_date,       expected_status)
    ("TODAY",          _date_str(0),           ReminderStatus.TODAY),
    ("TOMORROW",       _date_str(1),           ReminderStatus.TOMORROW),
    ("THIS_WEEK+2",    _date_str(2),           ReminderStatus.THIS_WEEK),
    ("THIS_WEEK+7",    _date_str(7),           ReminderStatus.THIS_WEEK),
    ("UPCOMING",       _date_str(8),           ReminderStatus.UPCOMING),
    ("OVERDUE-1",      _date_str(-1),          ReminderStatus.OVERDUE),
    ("OVERDUE-10",     _date_str(-10),         ReminderStatus.OVERDUE),
    ("NOT_SCHEDULED",  None,                   ReminderStatus.NOT_SCHEDULED),
]


def test_reminder_statuses():
    """pytest-compatible: all status computations are correct."""
    for label, date_str, expected_status in CASES:
        result = compute_reminder(date_str, "Not specified")
        assert result.status == expected_status, (
            f"[{label}] Expected {expected_status}, got {result.status} "
            f"(date={date_str})"
        )


def test_today_days_remaining():
    result = compute_reminder(_date_str(0), "11:00 AM")
    assert result.days_remaining == 0


def test_tomorrow_days_remaining():
    result = compute_reminder(_date_str(1), "Not specified")
    assert result.days_remaining == 1


def test_overdue_days_remaining_negative():
    result = compute_reminder(_date_str(-5), "3:00 PM")
    assert result.days_remaining is not None and result.days_remaining < 0


def test_not_scheduled_has_no_days():
    result = compute_reminder(None, "Not specified")
    assert result.days_remaining is None


def test_reminder_message_non_empty():
    """Every case must produce a non-empty message."""
    for label, date_str, _ in CASES:
        result = compute_reminder(date_str, "Not specified")
        assert result.reminder_message, f"[{label}] reminder_message is empty"


if __name__ == "__main__":
    print("\nReminder status tests\n" + "─" * 50)
    all_ok = True
    for label, date_str, expected in CASES:
        result = compute_reminder(date_str, "Not specified")
        ok = result.status == expected
        status = "OK  " if ok else "FAIL"
        print(f"  {status}  [{label:<16}]  got={result.status.value:<14}  expected={expected.value}")
        if not ok:
            all_ok = False
    print()
    print("All passed." if all_ok else "SOME TESTS FAILED.")
