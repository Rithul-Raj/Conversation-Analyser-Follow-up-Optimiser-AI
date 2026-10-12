"""
Windows toast notification service for FollowUp AI.

Fires a pop-up notification with sound when a lead's scheduled
follow-up date matches today. Called automatically after every
conversation analysis — no manual trigger required.

Dependency: winotify  (pip install winotify)
Platform   : Windows only. On non-Windows systems the function
             silently returns False so the CLI stays cross-platform.
"""

import sys
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Date format used throughout the model ("DD Mon YYYY", e.g. "11 Oct 2026")
# ---------------------------------------------------------------------------
_DATE_FORMAT = "%d %b %Y"


def notify_if_due_today(
    lead_id: str,
    scheduled_followup_date: str | None,
    scheduled_followup_time: str,
    recommended_action: str,
    motive_summary: str,
    bde_id: str = "",
) -> bool:
    """
    Show a Windows toast notification with sound if the scheduled
    follow-up date is today.

    Args:
        lead_id               : Normalised lead identifier (e.g. LEAD-001).
        scheduled_followup_date: Date string in "DD Mon YYYY" format, or None.
        scheduled_followup_time: Time string (e.g. "11:00 AM", "Morning").
        recommended_action    : The AI-recommended next action.
        motive_summary        : One-sentence motive from the AI analysis.
        bde_id                : BDE identifier — shown in the notification.

    Returns:
        True  if notification was shown (date is today).
        False if date is not today, not set, or platform is non-Windows.
    """
    # Only works on Windows
    if sys.platform != "win32":
        return False

    # No date committed in the conversation
    if not scheduled_followup_date:
        return False

    # Parse the date
    try:
        target_date = datetime.strptime(
            scheduled_followup_date.strip(), _DATE_FORMAT
        ).date()
    except ValueError:
        return False  # Unparseable date — skip silently

    # Only fire if the follow-up is due today
    if target_date != date.today():
        return False

    # ── Build notification content ─────────────────────────────────────────
    try:
        from winotify import Notification, audio
    except ImportError:
        # winotify not installed — degrade gracefully
        print(
            "\n  [NOTIFICATION] Follow-up due today! "
            f"Install winotify for pop-up alerts. "
            f"(pip install winotify)"
        )
        return False

    # Title
    title = f"Follow-up Due Today — {lead_id}"

    # Body: time on first line, action on second, motive truncated
    time_line   = f"Time   : {scheduled_followup_time}"
    action_line = f"Action : {recommended_action.replace('_', ' ').title()}"
    motive_line = (
        motive_summary[:120] + "..."
        if len(motive_summary) > 120
        else motive_summary
    )
    bde_line = f"BDE    : {bde_id}" if bde_id else ""

    body_parts = [time_line, action_line]
    if bde_line:
        body_parts.append(bde_line)
    body_parts.append(motive_line)
    message = "\n".join(body_parts)

    # ── Create and show the toast ──────────────────────────────────────────
    toast = Notification(
        app_id="FollowUp AI",
        title=title,
        msg=message,
        duration="long",   # stays visible longer (25 seconds)
    )
    toast.set_audio(audio.Reminder, loop=False)  # clock-chime sound
    toast.show()

    return True
