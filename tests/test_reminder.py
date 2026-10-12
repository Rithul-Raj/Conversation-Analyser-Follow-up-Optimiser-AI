"""Test the /reminder-status endpoint and the reminder block in /analyze-conversation."""
import json
import time
import requests

BASE = "http://localhost:8000"

def test_reminder_endpoint():
    print("\n=== POST /reminder-status (pure Python, no AI) ===\n")
    cases = [
        ("UPCOMING",       {"scheduled_followup_date": "24 Sep 2026", "scheduled_followup_time": "11:00 AM"}),
        ("TODAY",          {"scheduled_followup_date": "10 Sep 2026", "scheduled_followup_time": "Morning"}),
        ("TOMORROW",       {"scheduled_followup_date": "11 Sep 2026", "scheduled_followup_time": "2:00 PM - 4:00 PM"}),
        ("THIS_WEEK",      {"scheduled_followup_date": "14 Sep 2026", "scheduled_followup_time": "Not specified"}),
        ("OVERDUE",        {"scheduled_followup_date": "05 Sep 2026", "scheduled_followup_time": "3:00 PM"}),
        ("NOT_SCHEDULED",  {"scheduled_followup_date": None,          "scheduled_followup_time": "Not specified"}),
    ]
    for label, payload in cases:
        r = requests.post(f"{BASE}/reminder-status", json=payload, timeout=5)
        d = r.json()
        print(f"[{label}] HTTP {r.status_code}")
        print(f"  status          : {d.get('status')}")
        print(f"  days_remaining  : {d.get('days_remaining')}")
        print(f"  reminder_message: {d.get('reminder_message', d.get('detail'))}")
        print()

def test_analyze_with_reminder():
    print("\n=== POST /analyze-conversation (reminder block included) ===\n")
    conv = (
        "Called Rahul Singh, VP Sales at NovaCorp. He liked the demo and is ready to move forward. "
        "He asked us to call him back in exactly 2 weeks to finalise pricing. "
        "He specifically said to call at 11 AM on that day."
    )
    r = requests.post(f"{BASE}/analyze-conversation", json={"conversation_text": conv}, timeout=30)
    if r.status_code == 200:
        d = r.json()
        print("  scheduled_followup_date:", d.get("scheduled_followup_date"))
        print("  scheduled_followup_time:", d.get("scheduled_followup_time"))
        print("  reminder block:")
        rem = d.get("reminder", {})
        print("    status          :", rem.get("status"))
        print("    days_remaining  :", rem.get("days_remaining"))
        print("    reminder_message:", rem.get("reminder_message"))
    else:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")

if __name__ == "__main__":
    test_reminder_endpoint()
    print("Waiting 5s before AI call...")
    time.sleep(5)
    test_analyze_with_reminder()
    print("\nDone.")
