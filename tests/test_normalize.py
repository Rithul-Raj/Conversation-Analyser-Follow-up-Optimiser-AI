"""
tests/test_normalize.py
-----------------------
Tests for ID, time, and date normalisation utilities.
Runs completely offline — no Gemini key or running server required.

Usage:
    pytest tests/test_normalize.py -v
    # or run directly:
    python tests/test_normalize.py
"""
import sys
sys.path.insert(0, ".")

from services.utils import normalize_lead_id, normalize_time_filter, normalize_date_input

# ─── Lead ID ───────────────────────────────────────────────────────────────

id_cases = [
    ("LEAD001",           "LEAD-001"),
    ("lead-001",          "LEAD-001"),
    ("Lead_001",          "LEAD-001"),
    ("LEAD-001",          "LEAD-001"),
    ("LEAD-TIMING-TEST",  "LEAD-TIMING-TEST"),
    ("lead-timing-test",  "LEAD-TIMING-TEST"),
    ("CRM042",            "CRM-042"),
    ("EMP-042",           "EMP-042"),
]

# ─── Time normalisation ─────────────────────────────────────────────────────

time_cases = [
    ("7 pm",    "7:00 pm"),
    ("7pm",     "7:00 pm"),
    ("7 PM",    "7:00 pm"),
    ("7PM",     "7:00 pm"),
    ("7:00 PM", "7:00 pm"),
    ("7:00pm",  "7:00 pm"),
    ("7:30 PM", "7:30 pm"),
    ("7:30pm",  "7:30 pm"),
    ("11 AM",   "11:00 am"),
    ("morning", "morning"),
    ("Morning", "morning"),
]

# ─── Date normalisation ─────────────────────────────────────────────────────

date_cases = [
    ("5 Sep 2026",  "05 Sep 2026"),
    ("05 Sep 2026", "05 Sep 2026"),
    ("5 sep 2026",  "05 Sep 2026"),
    ("12 Oct 2026", "12 Oct 2026"),
    ("1 Jan 2027",  "01 Jan 2027"),
]

# ─── Schema date normaliser (LLMAnalysisOutput.normalise_date_format) ────────

schema_date_cases = [
    # (input,               expected_output)
    ("20 October 2026",    "20 Oct 2026"),   # full month name
    ("2026-10-20",         "20 Oct 2026"),   # ISO format
    ("October 20, 2026",   "20 Oct 2026"),   # long month, comma
    ("Oct 20, 2026",       "20 Oct 2026"),   # abbreviated month, comma
    ("20/10/2026",         "20 Oct 2026"),   # DD/MM/YYYY
    ("31 Feb 2026",        None),             # impossible date → None
    ("banana",             None),             # garbage → None
    ("tomorrow",           None),             # relative date → None
    (None,                 None),             # already None → None
]


def run_section(title, cases, fn):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")
    all_ok = True
    for raw, expected in cases:
        result = fn(raw)
        ok = result == expected
        status = "OK  " if ok else "FAIL"
        print(f"  {status}  {raw!r:<16} -> {result!r:<16}  expected: {expected!r}")
        all_ok = all_ok and ok
    return all_ok


def test_lead_id_normalisation():
    """pytest-compatible: all ID normalisations pass."""
    for raw, expected in id_cases:
        assert normalize_lead_id(raw) == expected, f"Failed for {raw!r}"


def test_time_normalisation():
    """pytest-compatible: all time normalisations pass."""
    for raw, expected in time_cases:
        assert normalize_time_filter(raw) == expected, f"Failed for {raw!r}"


def test_date_normalisation():
    """pytest-compatible: all date normalisations pass."""
    for raw, expected in date_cases:
        assert normalize_date_input(raw) == expected, f"Failed for {raw!r}"


def test_schema_date_normaliser():
    """pytest: schema-level date normaliser converts formats and returns None for bad dates."""
    from schemas.conversation_analysis import LLMAnalysisOutput, SalesStage, Priority, RecommendedAction, ConversationMode
    base_data = dict(
        sales_stage=SalesStage.EVALUATION,
        priority=Priority.MEDIUM,
        recommended_action=RecommendedAction.SEND_DOCUMENTATION,
        conversation_mode=ConversationMode.PROFESSIONAL,
        motive_summary="Test",
        scheduled_followup_time="11:00 AM",
        client_pain_points=[],
        client_recommendations=[],
    )
    for raw, expected in schema_date_cases:
        data = {**base_data, "scheduled_followup_date": raw}
        obj = LLMAnalysisOutput.model_validate(data)
        assert obj.scheduled_followup_date == expected, (
            f"Schema normaliser failed for {raw!r}: got {obj.scheduled_followup_date!r}, "
            f"expected {expected!r}"
        )


if __name__ == "__main__":
    all_passed = True
    all_passed &= run_section("Lead ID normalisation", id_cases, normalize_lead_id)
    all_passed &= run_section("Time filter normalisation", time_cases, normalize_time_filter)
    all_passed &= run_section("Date input normalisation", date_cases, normalize_date_input)
    print()
    print("All passed." if all_passed else "SOME TESTS FAILED.")
