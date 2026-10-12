"""
Shared utility functions used by both cli.py and main.py.
"""
import re


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
