"""
Comprehensive test for all scheduled_followup_time formats.
Run after uvicorn is started:  python tests/test_date_extraction.py
"""
import sys
import time
import requests

# Force UTF-8 output so any unicode characters don't crash on Windows terminals
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/analyze-conversation"

TESTS = [
    # ── Rule 1: Exact single time ───────────────────────────────────────────
    {
        "rule":  "Rule 1 – Exact time (11 AM)",
        "expect": "11:00 AM",
        "text":  "Client Rahul said call him back in 2 weeks at 11 AM to finalise pricing.",
    },
    {
        "rule":  "Rule 1 – Exact time (2:30 PM)",
        "expect": "2:30 PM",
        "text":  "Priya asked us to schedule the demo for next Monday at 2:30 PM.",
    },
    {
        "rule":  "Rule 1 – Worded time (half past 3)",
        "expect": "3:30 PM",
        "text":  "Arjun said call him on 20th September at half past 3 in the afternoon.",
    },
    # ── Rule 2: Time range ──────────────────────────────────────────────────
    {
        "rule":  "Rule 2 – Time range (11 AM to 3 PM)",
        "expect": "11:00 AM - 3:00 PM",
        "text":  "Client said call after two weeks at 11 AM to 3 PM, any time in that window works.",
    },
    {
        "rule":  "Rule 2 – Time range (between 9 and 11 AM)",
        "expect": "9:00 AM - 11:00 AM",
        "text":  "Sunita asked us to reach out next Friday between 9 and 11 AM.",
    },
    {
        "rule":  "Rule 2 – Time range (from 2 to 4 PM)",
        "expect": "2:00 PM - 4:00 PM",
        "text":  "Karan is available from 2 PM to 4 PM next Thursday for the product walk-through.",
    },
    # ── Rule 3: Vague time of day ────────────────────────────────────────────
    {
        "rule":  "Rule 3 – Vague: morning",
        "expect": "Morning",
        "text":  "Deepa said she prefers a morning call next week, no specific time given.",
    },
    {
        "rule":  "Rule 3 – Vague: afternoon",
        "expect": "Afternoon",
        "text":  "Ramesh mentioned he is free in the afternoon on 15th for a follow-up call.",
    },
    {
        "rule":  "Rule 3 – Vague: evening",
        "expect": "Evening",
        "text":  "Meena said she is usually only free in the evenings after office hours.",
    },
    {
        "rule":  "Rule 3 – Vague: end of day",
        "expect": "Evening",
        "text":  "Client asked us to call him at end of day on 25th September.",
    },
    # ── Rule 4: No time at all ───────────────────────────────────────────────
    {
        "rule":  "Rule 4 – No time mentioned",
        "expect": "Not specified",
        "text":  "Spoke with David Chen. He wants to meet next week but did not mention any time.",
    },
    {
        "rule":  "Rule 4 – No date or time at all",
        "expect": "Not specified",
        "text":  "Quick intro call with a new lead. No commitments made. Just sent product brochure.",
    },
]


def run():
    print(f"\n{'='*70}")
    print("  SCHEDULED_FOLLOWUP_TIME -- Comprehensive Format Tests")
    print(f"{'='*70}")

    passed = 0
    BATCH_SIZE = 6  # pause after every 6 calls to reset the 1-minute rate limit window

    for i, t in enumerate(TESTS, 1):
        # Pause between individual calls
        if i > 1:
            time.sleep(7)
        # After each full batch, wait a full minute for rate limit reset
        if i > 1 and (i - 1) % BATCH_SIZE == 0:
            print(f"\n  [Batch complete — waiting 65s for rate limit reset...]")
            time.sleep(65)
        try:
            r = requests.post(BASE, json={"conversation_text": t["text"]}, timeout=40)
            data = r.json()
            if r.status_code == 429:
                print(f"\n[{i}] {t['rule']}")
                print(f"    RATE LIMITED - wait and retry")
                continue
            if r.status_code != 200:
                print(f"\n[{i}] {t['rule']}")
                print(f"    ERROR {r.status_code}: {data}")
                continue

            time_val = data.get("scheduled_followup_time", "MISSING")
            date_val = data.get("scheduled_followup_date", "null")
            ok = "[PASS]" if t["expect"].lower() in str(time_val).lower() else "[FAIL]"
            if ok == "[PASS]":
                passed += 1

            print(f"\n[{i}] {t['rule']}")
            print(f"    Expected : {t['expect']}")
            print(f"    Got      : {time_val}  {ok}")
            print(f"    Date     : {date_val}")

        except Exception as e:
            print(f"\n[{i}] {t['rule']}")
            print(f"    EXCEPTION: {e}")

    print(f"\n{'='*70}")
    print(f"  Result: {passed}/{len(TESTS)} passed")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run()
