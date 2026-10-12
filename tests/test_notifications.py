"""
Test all 3 notification endpoints.
No AI call — pure Python, instant.
Run: python tests/test_notifications.py
"""
import sys
import json
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8000"

# Sample lead entries — simulating what a BDE would have stored
ENTRIES = [
    {"client_name": "David Chen",   "client_id": "CRM-001", "scheduled_followup_date": "21 Sep 2026", "scheduled_followup_time": "11:00 AM",          "notes": "Pricing discussion"},
    {"client_name": "Priya Nair",   "client_id": "CRM-002", "scheduled_followup_date": "22 Sep 2026", "scheduled_followup_time": "Morning",            "notes": "Demo follow-up"},
    {"client_name": "Rahul Singh",  "client_id": "CRM-003", "scheduled_followup_date": "21 Sep 2026", "scheduled_followup_time": "2:00 PM - 4:00 PM",  "notes": "Contract review"},
    {"client_name": "Anjali Desai", "client_id": "CRM-004", "scheduled_followup_date": "10 Sep 2026", "scheduled_followup_time": "3:00 PM",            "notes": "Overdue - missed last week"},
    {"client_name": "Vikram Soni",  "client_id": "CRM-005", "scheduled_followup_date": None,          "scheduled_followup_time": "Not specified",       "notes": "No commitment yet"},
    {"client_name": "Nisha Verma",  "client_id": "CRM-006", "scheduled_followup_date": "28 Sep 2026", "scheduled_followup_time": "Afternoon",          "notes": "Upcoming - eval stage"},
]

SEP = "=" * 65


def show(label, r):
    print(f"\n{SEP}")
    print(f"  {label}  [HTTP {r.status_code}]")
    print(SEP)
    if r.status_code == 200:
        data = r.json()
        if not data:
            print("  (no matching leads)")
        for item in data:
            rem = item.get("reminder", {})
            print(f"  Client : {item['client_name']} ({item.get('client_id', '-')})")
            print(f"  Date   : {item.get('scheduled_followup_date', 'None')}  |  Time: {item.get('scheduled_followup_time')}")
            print(f"  Status : {rem.get('status')}  |  Days: {rem.get('days_remaining')}")
            print(f"  Msg    : {rem.get('reminder_message')}")
            if item.get("notes"):
                print(f"  Notes  : {item['notes']}")
            print()
    else:
        print(" ", r.json())


# ── Test 1: by-date (date only) ──────────────────────────────────────────────
r = requests.post(f"{BASE}/notifications/by-date",
    json={"date": "21 Sep 2026", "entries": ENTRIES}, timeout=5)
show("1. /notifications/by-date  →  date=21 Sep 2026", r)

# ── Test 2: by-date with time filter ─────────────────────────────────────────
r = requests.post(f"{BASE}/notifications/by-date",
    json={"date": "21 Sep 2026", "time": "11:00 AM", "entries": ENTRIES}, timeout=5)
show("2. /notifications/by-date  →  date=21 Sep 2026, time=11:00 AM", r)

# ── Test 3: daily summary ─────────────────────────────────────────────────────
r = requests.post(f"{BASE}/notifications/daily",
    json={"entries": ENTRIES}, timeout=5)
show("3. /notifications/daily  →  OVERDUE + TODAY + TOMORROW", r)

# ── Test 4: client search by name (partial) ───────────────────────────────────
r = requests.post(f"{BASE}/notifications/client",
    json={"identifier": "david", "entries": ENTRIES}, timeout=5)
show("4. /notifications/client  →  identifier='david'", r)

# ── Test 5: client search by ID ───────────────────────────────────────────────
r = requests.post(f"{BASE}/notifications/client",
    json={"identifier": "CRM-006", "entries": ENTRIES}, timeout=5)
show("5. /notifications/client  →  identifier='CRM-006'", r)

# ── Test 6: client not found ──────────────────────────────────────────────────
r = requests.post(f"{BASE}/notifications/client",
    json={"identifier": "unknown_xyz", "entries": ENTRIES}, timeout=5)
show("6. /notifications/client  →  identifier='unknown_xyz' (expect 404)", r)

print(f"\n{SEP}\nAll tests done.\n{SEP}\n")
