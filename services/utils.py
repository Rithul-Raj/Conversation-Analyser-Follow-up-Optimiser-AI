"""
Shared utility functions used by both cli.py and main.py.
"""
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def normalize_lead_id(raw: str) -> str:
    """
    Canonical form for any lead or BDE identifier.

    Rules applied in order:
      1. Strip surrounding whitespace and uppercase.
      2. Replace all separators (spaces, hyphens, underscores) with a
         single hyphen — this preserves explicit word boundaries.
      3. Within each segment, insert a hyphen at every letter→digit or
         digit→letter boundary (handles LEAD001 → LEAD-001).

    Examples:
      LEAD001          → LEAD-001
      lead-001         → LEAD-001
      Lead_001         → LEAD-001
      LEAD-001         → LEAD-001
      CRM042           → CRM-042
      EMP-042          → EMP-042
      LEAD-TIMING-TEST → LEAD-TIMING-TEST
      lead-timing-test → LEAD-TIMING-TEST
    """
    if not raw:
        return ""
    # Step 1: uppercase, replace all separator characters with a single hyphen
    cleaned = raw.strip().upper()
    cleaned = re.sub(r"[\s_\-]+", "-", cleaned).strip("-")
    # Step 2: split into word segments on the normalised hyphens
    segments = cleaned.split("-")
    # Step 3: within each segment insert hyphens at letter↔digit boundaries
    parts = []
    for seg in segments:
        parts.extend(re.findall(r"[A-Z]+|[0-9]+", seg))
    return "-".join(parts)


def normalize_bde_id(raw: str) -> str:
    """Same normalisation rules as normalize_lead_id."""
    return normalize_lead_id(raw)


def normalize_time_filter(raw: str) -> str:
    """
    Standardise a user-typed time filter so it matches AI-extracted times.

    Handles the common mismatch where the user types "7 pm" but the
    stored value is "7:00 PM".

    Rules (applied in order):
      "7 pm"    → "7:00 pm"      (adds :00 when minutes are omitted)
      "7PM"     → "7:00 pm"      (space-insensitive, lowercase)
      "7:30pm"  → "7:30 pm"      (adds space before am/pm)
      "7:00 PM" → "7:00 pm"      (already correct, just lowercased)
      "morning" → "morning"      (vague words pass through unchanged)
    """
    t = raw.strip().lower()
    # Insert :00 when hour is given with no minutes, e.g. "7 pm" or "7pm"
    t = re.sub(r'^(\d{1,2})\s*(am|pm)$', r'\1:00 \2', t)
    # Ensure space between digits and am/pm, e.g. "7:30pm" → "7:30 pm"
    t = re.sub(r'^(\d{1,2}:\d{2})\s*(am|pm)$', r'\1 \2', t)
    return t


def normalize_date_input(raw: str) -> str:
    """
    Ensure a 'DD Mon YYYY' date string has a zero-padded day.

    The AI always stores dates with a 2-digit day ("05 Sep 2026"), but
    users naturally type single-digit days ("5 Sep 2026"). This function
    makes both forms identical before comparison.

    Examples:
      "5 Sep 2026"  → "05 Sep 2026"
      "05 Sep 2026" → "05 Sep 2026"
      "12 Oct 2026" → "12 Oct 2026"
    """
    parts = raw.strip().split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            return f"{day:02d} {parts[1].capitalize()} {parts[2]}"
        except ValueError:
            pass
    return raw.strip()


def get_today() -> date:
    """Return today's date in the project timezone (TIMEZONE env var, default Asia/Kolkata)."""
    tz_name = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone(timedelta(hours=5, minutes=30))  # IST fixed offset fallback
    return datetime.now(tz=tz).date()
