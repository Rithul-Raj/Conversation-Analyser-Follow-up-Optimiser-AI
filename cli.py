"""
Conversation Intelligence AI - BDE Terminal
============================================
Run from the conversation_ai/ directory:
    python cli.py

Standalone - no server needed. Imports services directly.
"""

import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from services.database import (
    get_all_leads,
    get_conversations_by_date,
    get_lead_count,
    get_lead_history,
    init_db,
    save_conversation,
)
from services.followup_rules import get_follow_up_days
from services.llm_client import analyze_conversation, ask_question
from services.reminder_service import compute_reminder
from services.toast_notifier import notify_if_due_today
from services.utils import normalize_bde_id, normalize_date_input, normalize_lead_id

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
W = 60   # display width

def line(char="-"):
    print("  " + char * W)

def header(title):
    print()
    print("  " + "=" * W)
    print(f"  {'Conversation Intelligence AI':^{W}}")
    print("  " + "=" * W)
    if title:
        print(f"  {title:^{W}}")
        print("  " + "-" * W)
    print()

def section(title):
    dashes = max(0, W - len(title) - 4)
    print(f"\n  -- {title} " + "-" * dashes)

def field(label, value, width=18):
    print(f"  {label:<{width}}: {value}")

def wrapped(label, text, width=18):
    prefix  = f"  {label:<{width}}: "
    rest    = " " * (len(prefix))
    wrapped_lines = textwrap.wrap(str(text), width=W - len(prefix) + 2)
    if wrapped_lines:
        print(prefix + wrapped_lines[0])
        for l in wrapped_lines[1:]:
            print(rest + l)

def bullet_list(label, items, width=18):
    if not items:
        return
    print(f"  {label:<{width}}:")
    for item in items:
        for l in textwrap.wrap(f"    * {item}", width=W):
            print(f"  {l}")

def get_multiline_input():
    print("  Paste conversation text below.")
    print("  When done, type  END  on a new line and press Enter.\n")
    lines = []
    while True:
        try:
            ln = input("  > ")
        except EOFError:
            break
        if ln.strip().upper() == "END":
            break
        lines.append(ln)
    return "\n".join(lines)

def pause():
    try:
        input("\n  Press Enter to return to menu...")
    except EOFError:
        pass

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
def show_menu():
    print()
    print("  " + "=" * W)
    print(f"  {'Conversation Intelligence AI  -  BDE Terminal':^{W}}")
    print("  " + "=" * W)
    print()
    print("    1   Analyse a conversation")
    print("    2   Ask a question about a conversation")
    print("    3   Find leads scheduled on a specific date")
    print("    4   View conversation history for a lead")
    print("    5   List all leads")
    print("    0   Exit")
    print()
    try:
        return input("  Choose (0-5): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "0"

# ---------------------------------------------------------------------------
# 1. Analyse conversation
# ---------------------------------------------------------------------------
def do_analyse():
    header("ANALYSE CONVERSATION")

    # ── Lead ID input with duplicate check ───────────────────────────
    while True:
        lead_id = normalize_lead_id(input("  Lead ID  : ").strip())
        if not lead_id:
            print("  ERROR: Lead ID cannot be empty.")
            continue

        # Check if this lead already has conversations stored
        recent = get_lead_history(lead_id, limit=1)   # lightweight: just latest record
        if recent:
            total    = get_lead_count(lead_id)         # exact count via COUNT(*)
            last     = recent[0]                        # only record returned = most recent
            date     = last["created_at"][:10]
            bde_prev = last["bde_id"]
            snippet  = last["conversation_text"][:70].replace("\n", " ")
            if len(last["conversation_text"]) > 70:
                snippet += "..."
            print()
            print(f"  ! Lead '{lead_id}' already exists  ({total} conversation(s))")
            print(f"    Last entry  : {date}  (BDE: {bde_prev})")
            print(f"    Snippet     : {snippet}")
            print()
            choice = input("  Continue adding to this lead? (Y / N): ").strip().upper()
            if choice == "Y":
                break          # proceed with the same lead_id
            elif choice == "N":
                print()
                continue       # loop back and ask for a different lead_id
            else:
                print("  Please enter Y or N.")
                continue
        else:
            break              # brand-new lead, proceed immediately

    bde_id = normalize_bde_id(input("  BDE ID   : ").strip())
    if not bde_id:
        print("\n  ERROR: BDE ID cannot be empty.")
        return
    print(f"  Using    \u2192  Lead: {lead_id}  |  BDE: {bde_id}")

    print()
    text = get_multiline_input()
    if len(text.strip()) < 20:
        print("\n  ERROR: Conversation text is too short.")
        return

    print("\n  Fetching history...", end="", flush=True)
    history = get_lead_history(lead_id, limit=5)  # re-fetch ordered correctly for AI context
    print(f" {len(history)} past conversation(s) found.")
    print("  Analysing with AI...", end="", flush=True)
    try:
        result = analyze_conversation(text, history=history)
    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        return
    print(" done.")

    follow_up_days = get_follow_up_days(result.priority)
    conv_id        = save_conversation(lead_id, bde_id, text, result.model_dump())
    reminder       = compute_reminder(
        result.scheduled_followup_date,
        result.scheduled_followup_time,
    )

    # ── Auto-notification: fires if follow-up is due today ────────────────
    notified = notify_if_due_today(
        lead_id                = lead_id,
        scheduled_followup_date= result.scheduled_followup_date,
        scheduled_followup_time= result.scheduled_followup_time,
        recommended_action     = result.recommended_action.value,
        motive_summary         = result.motive_summary,
        bde_id                 = bde_id,
    )
    if notified:
        print("  * Notification sent — follow-up is due TODAY.")

    section("RESULT")
    field("Lead ID",          lead_id)
    field("BDE ID",           bde_id)
    field("Sales Stage",      result.sales_stage.value)
    field("Priority",         result.priority.value)
    field("Recommended",      result.recommended_action.value)
    field("Mode",             result.conversation_mode.value)
    field("Follow-up in",     f"{follow_up_days} day(s)")
    field("Sched. Date",      result.scheduled_followup_date or "Not specified")
    field("Sched. Time",      result.scheduled_followup_time)
    field("Reminder",         f"{reminder.status.value}  ({reminder.days_remaining if reminder.days_remaining is not None else 'N/A'} day(s))")
    field("History Used",     f"{len(history)} past conversation(s)")
    field("Saved as",         f"Conversation #{conv_id}")

    section("MOTIVE SUMMARY")
    for ln in textwrap.wrap(result.motive_summary or "Not available.", width=W):
        print(f"  {ln}")

    if result.client_pain_points:
        section("CLIENT PAIN POINTS")
        for item in result.client_pain_points:
            for ln in textwrap.wrap(f"* {item}", width=W):
                print(f"  {ln}")

    if result.client_recommendations:
        section("CLIENT REQUESTS")
        for item in result.client_recommendations:
            for ln in textwrap.wrap(f"* {item}", width=W):
                print(f"  {ln}")

    line()

# ---------------------------------------------------------------------------
# 2. Ask a question
# ---------------------------------------------------------------------------
def do_ask():
    header("ASK ABOUT A CONVERSATION")

    print("  How would you like to provide the conversation?\n")
    print("    A   Paste conversation text manually")
    print("    B   Use a stored lead's conversations (enter Lead ID)")
    print()
    mode = input("  Choose (A / B): ").strip().upper()

    # ── Mode A: manual paste ──────────────────────────────────────────
    if mode == "A":
        print()
        text = get_multiline_input()
        if len(text.strip()) < 20:
            print("\n  ERROR: Conversation text is too short.")
            return
        context_label = "pasted conversation"

    # ── Mode B: load from lead ID ─────────────────────────────────────
    elif mode == "B":
        lead_id = normalize_lead_id(input("\n  Lead ID: ").strip())
        if not lead_id:
            print("\n  ERROR: Lead ID is required.")
            return
        print(f"  Using Lead ID: {lead_id}")

        history = get_lead_history(lead_id, limit=10)
        if not history:
            print(f"\n  No conversations found for lead '{lead_id}'.")
            return

        # Show a brief preview so the BDE can confirm these are the right records
        print(f"\n  {len(history)} conversation(s) loaded for Lead: {lead_id}\n")
        for i, h in enumerate(history, 1):
            date    = h["created_at"][:10]
            bde     = h["bde_id"]
            snippet = h["conversation_text"][:80].replace("\n", " ")
            if len(h["conversation_text"]) > 80:
                snippet += "..."
            print(f"  [{i}]  {date}  BDE: {bde}")
            print(f"        {snippet}")
        print()

        # Combine all conversations into one context block (oldest first)
        parts = []
        for i, h in enumerate(history, 1):
            date = h["created_at"][:10]
            parts.append(
                f"[Conversation {i} — {date} | BDE: {h['bde_id']}]\n"
                f"{h['conversation_text']}"
            )
        text = "\n\n".join(parts)
        context_label = f"lead '{lead_id}' ({len(history)} conversation(s))"


    else:
        print("\n  Invalid choice. Enter A or B.")
        return

    print()
    question = input("  Your question: ").strip()
    if not question:
        print("\n  ERROR: Question cannot be empty.")
        return

    print(f"\n  Asking AI about {context_label}...", end="", flush=True)
    try:
        answer = ask_question(text, question)
    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        return
    print(" done.")

    section("ANSWER")
    print()
    for ln in textwrap.wrap(answer, width=W):
        print(f"  {ln}")
    line()


# ---------------------------------------------------------------------------
# 3. Find leads by date
# ---------------------------------------------------------------------------
def do_find_by_date():
    header("FIND LEADS BY DATE")

    date_str = input("  Date (e.g. 24 Sep 2026): ").strip()
    if not date_str:
        print("\n  ERROR: Date is required.")
        return
    # Normalize: capitalize month, zero-pad day ("5 Sep" → "05 Sep 2026")
    date_str = normalize_date_input(date_str)

    time_str = input("  Time filter (optional, press Enter to skip): ").strip() or None

    results = get_conversations_by_date(date_str, time_str)

    if not results:
        msg = f"No leads found scheduled for {date_str}"
        if time_str:
            msg += f" at {time_str}"
        print(f"\n  {msg}.")
        return

    label = f"Found {len(results)} lead(s) scheduled for {date_str}"
    if time_str:
        label += f" | Time filter: {time_str}"
    section(label)
    print()

    for i, r in enumerate(results, 1):
        a = r["analysis"]
        print(f"  [{i}]  Lead: {r['lead_id']}   BDE: {r['bde_id']}")
        field("      Time",     a.get("scheduled_followup_time", "Not specified"), width=10)
        field("      Stage",    a.get("sales_stage", "-"),  width=10)
        field("      Priority", a.get("priority", "-"),     width=10)
        field("      Action",   a.get("recommended_action", "-"), width=10)
        motive = a.get("motive_summary", "")
        if motive:
            wrapped("      Motive", motive, width=12)
        print()

    line()

# ---------------------------------------------------------------------------
# 4. Lead conversation history
# ---------------------------------------------------------------------------
def do_lead_history():
    header("LEAD CONVERSATION HISTORY")

    lead_id = normalize_lead_id(input("  Lead ID: ").strip())
    if not lead_id:
        print("\n  ERROR: Lead ID is required.")
        return
    print(f"  Using Lead ID: {lead_id}")

    history = get_lead_history(lead_id, limit=10)
    if not history:
        print(f"\n  No conversations found for lead '{lead_id}'.")
        return

    section(f"{len(history)} conversation(s) for Lead: {lead_id}")
    print()

    for i, h in enumerate(history, 1):
        a    = h["analysis"]
        date = h["created_at"][:10]
        print(f"  [{i}]  Date: {date}   BDE: {h['bde_id']}")
        field("       Stage",    a.get("sales_stage"),          width=10)
        field("       Priority", a.get("priority"),             width=10)
        field("       Action",   a.get("recommended_action"),   width=10)
        sched = a.get("scheduled_followup_date")
        if sched:
            field("       Sched",  f"{sched} at {a.get('scheduled_followup_time', '')}", width=10)
        motive = a.get("motive_summary", "")
        if motive:
            wrapped("       Motive", motive, width=13)
        pain = a.get("client_pain_points", [])
        if pain:
            pts = ", ".join(pain[:2]) + (" ..." if len(pain) > 2 else "")
            wrapped("       Pain pts", pts, width=13)
        print()

    line()

# ---------------------------------------------------------------------------
# 5. List all leads
# ---------------------------------------------------------------------------
def do_list_leads():
    header("ALL LEADS")

    leads = get_all_leads()
    if not leads:
        print("  No leads in the database yet.")
        return

    print(f"  {len(leads)} lead(s) on record:\n")
    print(f"  {'Lead ID':<22} {'Conversations':>13}  Last Contact")
    print(f"  {'-'*22} {'-'*13}  {'-'*12}")
    for l in leads:
        last = l.get("last_interaction", "")[:10]
        print(f"  {l['lead_id']:<22} {l['total_interactions']:>13}  {last}")

    line()

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    init_db()
    actions = {
        "1": do_analyse,
        "2": do_ask,
        "3": do_find_by_date,
        "4": do_lead_history,
        "5": do_list_leads,
    }
    while True:
        try:
            choice = show_menu()
        except (EOFError, KeyboardInterrupt):
            choice = "0"

        if choice == "0":
            print("\n  Goodbye.\n")
            break
        elif choice in actions:
            try:
                actions[choice]()
            except KeyboardInterrupt:
                print("\n  Cancelled.")
            pause()
        else:
            print("\n  Invalid option. Please enter a number from 0 to 5.")
            pause()


if __name__ == "__main__":
    main()
