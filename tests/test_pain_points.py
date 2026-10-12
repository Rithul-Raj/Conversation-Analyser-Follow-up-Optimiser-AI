"""
Targeted test for client_pain_points and client_recommendations.
Tests the 3 new conversations (ids 11, 12, 13) only — saves API quota.
Run from conversation_ai/:  python tests/test_pain_points.py
"""
import sys
import time
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8000/analyze-conversation"

CASES = [
    {
        "id": 11,
        "label": "Rich pain points + recommendations",
        "expect_pain": True,
        "expect_rec": True,
        "text": (
            "Call with Nisha Verma, Head of Operations at FastFreight Logistics. "
            "She said their current software crashes every time more than 50 users "
            "log in simultaneously. She also mentioned that their reporting module "
            "is outdated and exports only to CSV, which wastes hours of manual work "
            "each week. She specifically asked us to include real-time dashboard "
            "support in any proposal we send. She also requested that we offer a "
            "30-day free pilot before they commit to an annual contract. She is "
            "genuinely evaluating us as a replacement for their current vendor."
        ),
    },
    {
        "id": 12,
        "label": "No pain points, no recommendations (early inquiry)",
        "expect_pain": False,
        "expect_rec": False,
        "text": (
            "Brief introductory call with Vikram Soni, Junior Associate at "
            "StartupHub India. He attended our webinar last week and followed up "
            "out of curiosity. He did not express any problems with existing tools, "
            "made no specific requests, and had no timeline or budget discussion. "
            "Just asked some general questions about what industries we serve. "
            "Polite conversation, no commitment made."
        ),
    },
    {
        "id": 13,
        "label": "One pain point + one recommendation",
        "expect_pain": True,
        "expect_rec": True,
        "text": (
            "Follow-up call with Anjali Desai, Procurement Manager at MegaMart Retail. "
            "She confirmed they want to move forward but raised one concern: "
            "their IT team found our onboarding process too complex for non-technical staff. "
            "She requested that we assign a dedicated onboarding specialist "
            "for the first 60 days post-contract. Price and features are not an "
            "issue — she just wants that support guarantee in writing."
        ),
    },
]


def run():
    print("\n" + "=" * 70)
    print("  client_pain_points & client_recommendations — Targeted Tests")
    print("=" * 70)

    passed = 0
    for i, c in enumerate(CASES, 1):
        if i > 1:
            time.sleep(8)
        print(f"\n[{c['id']}] {c['label']}")
        r = requests.post(BASE, json={"conversation_text": c["text"]}, timeout=40)
        if r.status_code == 429:
            print("  RATE LIMITED — wait and retry later")
            continue
        if r.status_code != 200:
            print(f"  ERROR {r.status_code}: {r.text[:200]}")
            continue

        d = r.json()
        pain = d.get("client_pain_points", [])
        recs = d.get("client_recommendations", [])
        pain_ok = bool(pain) == c["expect_pain"]
        rec_ok  = bool(recs) == c["expect_rec"]
        ok = "[PASS]" if (pain_ok and rec_ok) else "[FAIL]"
        if ok == "[PASS]":
            passed += 1

        print(f"  client_pain_points     ({len(pain)} items): {pain}")
        print(f"  client_recommendations ({len(recs)} items): {recs}")
        print(f"  Result: {ok}")

    print(f"\n{'='*70}")
    print(f"  Result: {passed}/{len(CASES)} passed")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run()
