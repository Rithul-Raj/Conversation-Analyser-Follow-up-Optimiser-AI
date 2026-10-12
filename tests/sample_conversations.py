"""
Manual test suite — 10 realistic sales conversations covering all major stages
and priority levels.

Usage (from the conversation_ai/ directory):
    python tests/sample_conversations.py

This calls the running FastAPI server at http://localhost:8000.
Run `uvicorn main:app --reload` in a separate terminal first.

No labeled ground truth exists (by design), so results are manually reviewed.
Expected outcomes are documented inline as comments for human verification.
"""

import json
import sys
import textwrap

import requests

BASE_URL = "http://localhost:8000"
ANALYZE_URL = f"{BASE_URL}/analyze-conversation"
ASK_URL = f"{BASE_URL}/ask-conversation"


# ---------------------------------------------------------------------------
# Sample conversations
# Each dict has: id, description, text, expected_stage_hint, expected_priority_hint
# These hints are for the human reviewer — not assertions that must pass programmatically.
# ---------------------------------------------------------------------------
SAMPLE_CONVERSATIONS = [
    {
        "id": 1,
        "description": "Brand-new lead, first inquiry, just exploring",
        "expected_hints": "AWARENESS / LOW / EXPLAIN_PRODUCT or SCHEDULE_DEMO",
        "text": textwrap.dedent("""\
            Spoke with Arjun Mehta from TechNova Solutions. He saw our LinkedIn post
            and reached out to understand what our platform does. He had no prior
            knowledge of our product and asked basic questions — 'What does your
            software actually do?' and 'Which industries use it?'. Very friendly tone,
            no specific requirements yet. He said he might share the info with his
            manager. No urgency mentioned.
        """),
    },
    {
        "id": 2,
        "description": "Interested lead asking for a demo, clear interest shown",
        "expected_hints": "INTEREST / MEDIUM / SCHEDULE_DEMO",
        "text": textwrap.dedent("""\
            Follow-up call with Priya Sharma, Operations Head at LogiCore Pvt Ltd.
            She remembered our earlier email and said she read through our brochure.
            She's interested in seeing the platform live and wants to understand
            the workflow automation features better. She asked if we can set up a
            product demo for her and her team next week. She mentioned they are
            evaluating 2-3 vendors but ours seems to fit their use case well.
        """),
    },
    {
        "id": 3,
        "description": "Deep evaluation — comparing against competitor, very detailed questions",
        "expected_hints": "EVALUATION / HIGH / SEND_DOCUMENTATION or ANSWER_OBJECTION",
        "text": textwrap.dedent("""\
            Detailed call with Ravi Teja, CTO of DataStream Inc. He has already
            seen our demo and is now in a head-to-head comparison with Salesforce.
            He asked very specific questions: Does our API support OAuth 2.0?
            What's the SLA for uptime? Can we handle 500K records per batch?
            He also asked for a technical comparison document and wanted to know
            our data residency policy for European clients. Tone was very technical
            and direct. He said a final decision will be made within 2 weeks.
        """),
    },
    {
        "id": 4,
        "description": "Active price negotiation — client wants discount",
        "expected_hints": "NEGOTIATION / HIGH / SEND_QUOTATION or CALL_CLIENT",
        "text": textwrap.dedent("""\
            Call with Sunita Rao, CFO of RetailMax Group. She confirmed they want
            to proceed with our enterprise plan but is pushing hard on price.
            She said their budget cap is 20% below our listed price. She asked
            if we can offer a volume discount for a 3-year contract. She also
            mentioned a competitor offered them a better rate last week and asked
            if we can match it. Clear buying intent — she just wants a better deal.
            She wants our revised quotation by end of week.
        """),
    },
    {
        "id": 5,
        "description": "Decision stage — internal approval in progress, awaiting sign-off",
        "expected_hints": "DECISION / HIGH / FOLLOW_UP or WAIT",
        "text": textwrap.dedent("""\
            Spoke with Amit Kapoor, VP Procurement at FinEdge Ltd. He confirmed
            the team is aligned on choosing our product. The proposal is now with
            their board for budget approval. He said the sign-off usually takes
            5-7 business days. He asked us not to send too many follow-ups but
            to be available if the board has questions. He was confident this
            will go through. No action needed except staying available.
        """),
    },
    {
        "id": 6,
        "description": "Closed deal — contract signed, onboarding discussion",
        "expected_hints": "CLOSED / LOW / WAIT or SEND_DOCUMENTATION",
        "text": textwrap.dedent("""\
            Final call with Meena Iyer, CEO of BuildSmart Technologies. Contract
            was signed yesterday. She called to discuss onboarding timelines and
            asked when the implementation team will reach out. She is happy with
            the deal and mentioned she may refer two other companies in her network.
            No objections, no open issues. Just coordination needed for smooth
            onboarding.
        """),
    },
    {
        "id": 7,
        "description": "Cold lead that went silent — low engagement, hard to reach",
        "expected_hints": "INTEREST / LOW / FOLLOW_UP or WAIT",
        "text": textwrap.dedent("""\
            Attempted to reconnect with Karan Bose from NexGen Retail. Last
            interaction was 3 weeks ago — he had initially asked for a demo but
            then stopped responding. Left a voicemail today, no callback yet.
            His assistant mentioned he's been very busy with an internal project.
            No strong buying signal, no rejection either. Relationship is lukewarm.
            Need to decide whether to keep nurturing or deprioritise.
        """),
    },
    {
        "id": 8,
        "description": "Technical objection — integration concern blocking progress",
        "expected_hints": "EVALUATION / HIGH / ESCALATE_TECHNICAL or ANSWER_OBJECTION",
        "text": textwrap.dedent("""\
            Video call with Suresh Pillai, Lead Developer at CloudCore Systems.
            He raised a serious concern: their legacy ERP system uses SOAP APIs
            and he's worried our platform only supports REST. He asked whether
            we have a SOAP adapter or a middleware layer. He also questioned our
            data migration process and whether downtime is expected during cutover.
            He was polite but firm — if integration doesn't work cleanly, they
            cannot proceed. Needs technical escalation urgently.
        """),
    },
    {
        "id": 9,
        "description": "Casual inbound — small business owner, exploring casually",
        "expected_hints": "AWARENESS / LOW / EXPLAIN_PRODUCT",
        "text": textwrap.dedent("""\
            WhatsApp message from Deepa Nair, owner of a boutique clothing store.
            She saw our Instagram ad and messaged asking 'hi, what does your app do?'
            Very casual conversation. She runs a small business with 3 employees.
            Not sure if she's the right customer profile but she seemed curious.
            Sent her a short overview. She said 'looks interesting, will check it out'.
            No follow-up commitment from her side.
        """),
    },
    {
        "id": 10,
        "description": "Escalation needed — unhappy client, at risk of churning",
        "expected_hints": "NEGOTIATION or DECISION / HIGH / ESCALATE_TECHNICAL or CALL_CLIENT",
        "text": textwrap.dedent("""\
            Angry call from Ramesh Gupta, IT Head at PharmaLink Corp. He is
            frustrated that promised features from our last contract renewal have
            not been delivered. He said if the issues are not resolved in 48 hours,
            he will escalate to his CEO and explore alternatives. He listed three
            specific unresolved bugs reported 2 weeks ago. Very agitated tone.
            Account is at risk. Needs immediate escalation internally.
        """),
    },
    # -----------------------------------------------------------------------
    # New cases: verifying client_pain_points & client_recommendations
    # -----------------------------------------------------------------------
    {
        "id": 11,
        "description": "Clear pain points + explicit recommendations from client",
        "expected_hints": "EVALUATION / HIGH / ANSWER_OBJECTION — pain_points & recommendations non-empty",
        "text": textwrap.dedent("""\
            Call with Nisha Verma, Head of Operations at FastFreight Logistics.
            She said their current software crashes every time more than 50 users
            log in simultaneously. She also mentioned that their reporting module
            is outdated and exports only to CSV, which wastes hours of manual work
            each week. She specifically asked us to include real-time dashboard
            support in any proposal we send. She also requested that we offer a
            30-day free pilot before they commit to an annual contract. She is
            genuinely evaluating us as a replacement for their current vendor.
        """),
    },
    {
        "id": 12,
        "description": "No pain points, no recommendations — early awareness inquiry",
        "expected_hints": "AWARENESS / LOW / EXPLAIN_PRODUCT — both lists should be empty []",
        "text": textwrap.dedent("""\
            Brief introductory call with Vikram Soni, Junior Associate at
            StartupHub India. He attended our webinar last week and followed up
            out of curiosity. He did not express any problems with existing tools,
            made no specific requests, and had no timeline or budget discussion.
            Just asked some general questions about what industries we serve.
            Polite conversation, no commitment made.
        """),
    },
    {
        "id": 13,
        "description": "Mixed: one pain point stated, one client recommendation",
        "expected_hints": "NEGOTIATION / HIGH / SEND_QUOTATION — one item in each list",
        "text": textwrap.dedent("""\
            Follow-up call with Anjali Desai, Procurement Manager at MegaMart
            Retail. She confirmed they want to move forward but raised one concern:
            their IT team found our onboarding process too complex for non-technical
            staff. She requested that we assign a dedicated onboarding specialist
            for the first 60 days post-contract. Price and features are not an
            issue — she just wants that support guarantee in writing.
        """),
    },
]

# ---------------------------------------------------------------------------
# Question for the Q&A endpoint test (run against conversation #3)
# ---------------------------------------------------------------------------
QA_TEST_CASES = [
    {
        "conversation_id": 3,
        "question": "What is the real motive of this conversation?",
    },
    {
        "conversation_id": 3,
        "question": "Is the client price-sensitive or feature-sensitive?",
    },
    {
        "conversation_id": 4,
        "question": "What should I avoid saying in the next follow-up?",
    },
    {
        "conversation_id": 10,
        "question": "How confident does the client sound about moving forward?",
    },
]


# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------
def separator(char="-", width=70):
    print(char * width)


def print_result(label: str, data: dict | str):
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")
    if isinstance(data, dict):
        print(json.dumps(data, indent=2))
    else:
        print(data)


def run_analyze_tests():
    print("\n\n" + "=" * 70)
    print("  STRUCTURED ANALYSIS TESTS  (/analyze-conversation)")
    print("=" * 70)

    for conv in SAMPLE_CONVERSATIONS:
        separator()
        print(f"\n[{conv['id']}] {conv['description']}")
        print(f"    Expected hints: {conv['expected_hints']}")

        try:
            resp = requests.post(
                ANALYZE_URL,
                json={"conversation_text": conv["text"]},
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            print("\n  AI Output:")
            print(f"    sales_stage:            {result.get('sales_stage')}")
            print(f"    priority:               {result.get('priority')}")
            print(f"    recommended_action:     {result.get('recommended_action')}")
            print(f"    conversation_mode:      {result.get('conversation_mode')}")
            print(f"    follow_up_days:         {result.get('follow_up_days')}")
            print(f"    motive_summary:         {result.get('motive_summary')}")
            print(f"    client_pain_points:     {result.get('client_pain_points')}")
            print(f"    client_recommendations: {result.get('client_recommendations')}")
        except requests.exceptions.ConnectionError:
            print("\n  ERROR: Could not connect to server. Is uvicorn running?")
            sys.exit(1)
        except requests.exceptions.HTTPError as exc:
            print(f"\n  HTTP ERROR {exc.response.status_code}: {exc.response.text}")
        except Exception as exc:
            print(f"\n  UNEXPECTED ERROR: {exc}")

    print()


def run_qa_tests():
    print("\n\n" + "=" * 70)
    print("  FREE-FORM Q&A TESTS  (/ask-conversation)")
    print("=" * 70)

    conv_map = {c["id"]: c for c in SAMPLE_CONVERSATIONS}

    for case in QA_TEST_CASES:
        conv = conv_map[case["conversation_id"]]
        separator()
        print(f"\n  Conversation [{case['conversation_id']}]: {conv['description']}")
        print(f"  Question: {case['question']}")

        try:
            resp = requests.post(
                ASK_URL,
                json={
                    "conversation_text": conv["text"],
                    "question": case["question"],
                },
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            print(f"\n  Answer: {result.get('answer')}")
        except requests.exceptions.ConnectionError:
            print("\n  ERROR: Could not connect to server. Is uvicorn running?")
            sys.exit(1)
        except requests.exceptions.HTTPError as exc:
            print(f"\n  HTTP ERROR {exc.response.status_code}: {exc.response.text}")
        except Exception as exc:
            print(f"\n  UNEXPECTED ERROR: {exc}")

    print()


if __name__ == "__main__":
    run_analyze_tests()
    run_qa_tests()
    print("\nAll tests complete. Review outputs above against expected hints.\n")
