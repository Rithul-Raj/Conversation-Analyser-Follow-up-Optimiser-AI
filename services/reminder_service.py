"""
Reminder service — pure Python, zero AI, zero API cost.

Given a scheduled_followup_date string (e.g. "24 Sep 2026") and an optional
scheduled_followup_time string, computes:
  - days_remaining  : int (negative = overdue)
  - reminder_status : ReminderStatus enum value
  - reminder_message: human-readable string for the BDE
"""

from datetime import date, datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Date format the AI always uses (DD Mon YYYY, e.g. "24 Sep 2026")
# ---------------------------------------------------------------------------
_DATE_FORMAT = "%d %b %Y"


class ReminderStatus(str, Enum):
    OVERDUE       = "OVERDUE"        # scheduled date has already passed
    TODAY         = "TODAY"          # follow-up is today
    TOMORROW      = "TOMORROW"       # follow-up is tomorrow
    THIS_WEEK     = "THIS_WEEK"      # within 2–7 days
    UPCOMING      = "UPCOMING"       # more than 7 days away
    NOT_SCHEDULED = "NOT_SCHEDULED"  # no date was committed in the conversation


class ReminderResult:
    """Plain data container — not a Pydantic model so it stays dependency-free."""

    def __init__(
        self,
        status: ReminderStatus,
        days_remaining: int | None,
        reminder_message: str,
    ):
        self.status          = status
        self.days_remaining  = days_remaining
        self.reminder_message = reminder_message

    def to_dict(self) -> dict:
        return {
            "status":           self.status.value,
            "days_remaining":   self.days_remaining,
            "reminder_message": self.reminder_message,
        }


def _status_from_days(days: int) -> ReminderStatus:
    if days < 0:
        return ReminderStatus.OVERDUE
    if days == 0:
        return ReminderStatus.TODAY
    if days == 1:
        return ReminderStatus.TOMORROW
    if days <= 7:
        return ReminderStatus.THIS_WEEK
    return ReminderStatus.UPCOMING


def _build_message(
    status: ReminderStatus,
    days: int,
    date_str: str,
    time_str: str,
) -> str:
    """Build a clear, human-readable message for the BDE."""
    time_part = f" at {time_str}" if time_str and time_str != "Not specified" else ""

    if status == ReminderStatus.OVERDUE:
        overdue_by = abs(days)
        day_word = "day" if overdue_by == 1 else "days"
        return (
            f"OVERDUE by {overdue_by} {day_word} — was scheduled for {date_str}{time_part}. "
            f"Contact the client immediately."
        )
    if status == ReminderStatus.TODAY:
        return f"Follow up TODAY — {date_str}{time_part}. Do not miss this."
    if status == ReminderStatus.TOMORROW:
        return f"Follow up TOMORROW — {date_str}{time_part}. Prepare your talking points."
    if status == ReminderStatus.THIS_WEEK:
        return f"Follow up in {days} days — {date_str}{time_part}. Keep the lead warm."
    # UPCOMING
    return f"Follow up in {days} days — {date_str}{time_part}. Schedule it in your calendar."


def compute_reminder(
    scheduled_followup_date: str | None,
    scheduled_followup_time: str = "Not specified",
) -> ReminderResult:
    """
    Compute the reminder status for a lead.

    Args:
        scheduled_followup_date: Date string in "DD Mon YYYY" format, or None.
        scheduled_followup_time: Time string (any format), or "Not specified".

    Returns:
        ReminderResult with status, days_remaining, and a human-readable message.
    """
    if not scheduled_followup_date:
        return ReminderResult(
            status=ReminderStatus.NOT_SCHEDULED,
            days_remaining=None,
            reminder_message=(
                "No specific follow-up date was committed in the conversation. "
                "Use follow_up_days as the default guideline."
            ),
        )

    try:
        target = datetime.strptime(scheduled_followup_date.strip(), _DATE_FORMAT).date()
    except ValueError:
        # Gracefully handle unexpected date formats — treat as not scheduled
        return ReminderResult(
            status=ReminderStatus.NOT_SCHEDULED,
            days_remaining=None,
            reminder_message=(
                f"Could not parse scheduled date '{scheduled_followup_date}'. "
                "Please verify the date format."
            ),
        )

    today      = date.today()
    days_delta = (target - today).days
    status     = _status_from_days(days_delta)
    message    = _build_message(status, days_delta, scheduled_followup_date, scheduled_followup_time)

    return ReminderResult(
        status=status,
        days_remaining=days_delta,
        reminder_message=message,
    )
