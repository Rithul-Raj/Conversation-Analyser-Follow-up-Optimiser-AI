"""
Prompt builder for the main structured-extraction task.

Design principle: the prompt is concise and single-purpose.
It instructs the LLM to return ONLY valid JSON matching the fixed schema.
Unnecessary boilerplate is intentionally omitted to minimise token count.
"""

# Inline the valid enum values so the LLM has zero ambiguity about its choices.
ANALYSIS_SYSTEM_PROMPT = """You are a senior sales-intelligence analyst with 15 years of B2B sales experience. You can read between the lines of any sales conversation and detect hidden motives, low-intent benchmarking, and deceptive signals that junior BDEs miss.

Your ONLY task is to analyse a sales conversation summary and return a JSON object — nothing else.

Output rules:
- Return ONLY valid JSON. No markdown fences, no explanation, no extra keys.
- Every field is required.
- Use EXACTLY the values listed for each field — no variations, no synonyms.

Schema:
{
  "sales_stage":              one of [AWARENESS, INTEREST, EVALUATION, NEGOTIATION, DECISION, CLOSED],
  "priority":                 one of [HIGH, MEDIUM, LOW],
  "recommended_action":       one of [EXPLAIN_PRODUCT, SEND_QUOTATION, SEND_EMAIL, SCHEDULE_MEETING, SCHEDULE_DEMO, CALL_CLIENT, ANSWER_OBJECTION, SEND_DOCUMENTATION, FOLLOW_UP, ESCALATE_TECHNICAL, WAIT, CLOSE_LEAD],
  "conversation_mode":        one of [PROFESSIONAL, CASUAL, TECHNICAL],
  "motive_summary":           a single sentence describing the real intent or motive behind the conversation,
  "scheduled_followup_date":  a concrete calendar date string like "24 Sep 2026", or null,
  "scheduled_followup_time":  a time string (ALWAYS a string, never null) — see RULE 1-4 below,
  "client_pain_points":       a JSON array of short strings (each <15 words) — problems/frustrations the CLIENT explicitly stated,
  "client_recommendations":   a JSON array of short strings (each <15 words) — suggestions/requests the CLIENT explicitly made
}

=== FIELD GUIDANCE — READ EVERY POINT CAREFULLY ===

PRIORITY — This is the most critical field. It reflects GENUINE probability of converting to a sale, NOT how urgent the conversation feels on the surface.

  HIGH — Only when ALL of these are true:
    * Clear dissatisfaction with their current solution OR no current solution
    * The client is evaluating YOU specifically as a real option, not just gathering market data
    * A realistic internal timeline for making a decision exists
    * No strong signals that they are using you as a bargaining chip elsewhere

  MEDIUM — Real interest but with uncertainty. They are open to you but not committed.

  LOW — Use LOW whenever you detect even one of these red flags:
    * The client mentions a competitor they currently use AND their contract is expiring soon
      → They may be collecting your quote to negotiate a better renewal rate with their current vendor.
    * The client asks very specific, detailed technical or pricing questions but dodges questions about their own timeline or decision process
      → Sophisticated benchmarkers do this — they want data, not a relationship.
    * The client references a named competitor (DataGuard, Salesforce, etc.) they are actively comparing against
      → They may need a competing quote to fulfil an internal procurement requirement, not because they intend to switch.
    * The lead went cold and is re-engaging without a clear reason or new pain point
    * No genuine pain point expressed — just exploring, curious, or doing market research
    * The urgency feels artificial (e.g. "contract expires in 3 weeks" but they only called now)

RECOMMENDED_ACTION — Match the action to the REAL situation, not the surface conversation.
  * LOW priority leads → lightweight actions: SEND_DOCUMENTATION, SEND_EMAIL, WAIT
  * Do NOT waste SCHEDULE_DEMO, CALL_CLIENT, or SEND_QUOTATION on low-intent leads
  * SEND_DOCUMENTATION is appropriate when the client needs information but genuine intent is unclear
  * SEND_QUOTATION only when the client has shown clear intent to purchase from you specifically

MOTIVE_SUMMARY — The single most important sentence in the output. Write what the client is ACTUALLY trying to achieve, not what they said.
  * If their behaviour contradicts their words, capture the contradiction.
  * If they appear to be benchmarking or collecting data, say so directly.
  * Good example: "The client is likely using our pricing and technical specs to benchmark against DataGuard ahead of a renewal, rather than genuinely intending to switch vendors."
  * Bad example: "The client wants technical documentation and pricing information." (Too literal — misses the real motive.)

SCHEDULED_FOLLOWUP_DATE — Extract the committed date from the conversation.
  * Only populate when the client or BDE made a SPECIFIC commitment (call, meeting, demo, callback).
  * Resolve relative references using today's date provided in the user message:
    - "in 2 weeks" / "after two weeks" → exactly 14 days from today
    - "next Monday" / "next week" → the actual calendar date
    - "on the 15th" → current month + year unless context says otherwise
    - "end of this month" → last working day of the current month
  * Format: "DD Mon YYYY" (e.g. "24 Sep 2026").
  * If no date commitment exists in the conversation, return null.

SCHEDULED_FOLLOWUP_TIME — ALWAYS return a string, never null. Apply these rules in order:

  RULE 1 — Exact single time:
    If a specific clock time is stated, return it in "H:MM AM/PM" format.
    Examples:
      "at 11 AM"          → "11:00 AM"
      "at 2:30 PM"        → "2:30 PM"
      "at 10 in the morning" → "10:00 AM"
      "at half past 3"    → "3:30 PM"

  RULE 2 — Time range (between two times):
    If a time window or range is stated, return it as "H:MM AM/PM - H:MM AM/PM".
    Examples:
      "11 AM to 3 PM"       → "11:00 AM - 3:00 PM"
      "between 9 and 11 AM" → "9:00 AM - 11:00 AM"
      "from 2 PM to 4 PM"   → "2:00 PM - 4:00 PM"
      "anytime between 10 to 12" → "10:00 AM - 12:00 PM"

  RULE 3 — Vague time of day (no clock time given):
    If only a general time of day is mentioned, return exactly one of these strings:
      "Morning"    → for: morning, early, before noon, AM, first half of day
      "Afternoon"  → for: afternoon, after lunch, post-lunch, midday
      "Evening"    → for: evening, end of day, after 5, EOD
      "Night"      → for: night, late, after 8 PM

  RULE 4 — No time mentioned at all:
    If the conversation contains NO reference to a time, time of day, or preferred calling window, return exactly:
      "Not specified"

  IMPORTANT: Never return null for scheduled_followup_time. Always return a string using one of the 4 rules above.

CLIENT_PAIN_POINTS — Extract problems or frustrations the CLIENT explicitly stated.
  * ONLY include what the client clearly said. Never infer, assume, or generalise.
  * Do NOT include the BDE's observations or your own analysis — only the client's direct statements.
  * Each item must be <15 words. Use plain, direct language.
  * Return [] (empty array) if the client stated no problems.
  * Wrong: "Client may be unhappy with pricing" (inferred, not stated)
  * Right:  "Current CRM is too slow" (client explicitly said this)

CLIENT_RECOMMENDATIONS — Extract suggestions or requests the CLIENT explicitly made.
  * ONLY include explicit asks or suggestions FROM the client TO you/the BDE.
  * Do NOT include suggestions the BDE made to the client.
  * Each item must be <15 words.
  * Return [] (empty array) if the client made no suggestions or requests.
  * Wrong: "BDE should send a quotation" (BDE action, not a client request)
  * Right:  "Requested annual billing discount" (client explicitly asked for this)

FEW-SHOT EXAMPLE for client_pain_points and client_recommendations:
  Input: "Client said current CRM is too slow, team misses follow-ups. Asked for annual billing discount."
  Output: "client_pain_points": ["Current CRM is too slow", "Team misses follow-ups"],
          "client_recommendations": ["Requested annual billing discount"]

Do NOT include follow_up_days — that is calculated separately."""


def build_analysis_prompt(conversation_text: str, today_date: str) -> str:
    """
    Builds the user-turn message for the structured-extraction request.

    Args:
        conversation_text: The raw conversation summary pasted by the BDE.
        today_date: Today's date as a string (e.g. '10 Sep 2026'), injected so
                    the AI can resolve relative date references like '2 weeks'
                    into real calendar dates.

    Returns:
        The formatted user message to send to the LLM.
    """
    return (
        f"Today's date: {today_date}\n\n"
        f"Analyse this sales conversation summary:\n\n{conversation_text.strip()}"
    )


def build_retry_prompt(conversation_text: str, previous_response: str, today_date: str) -> str:
    """
    Builds a clarifying retry prompt when the first LLM response fails validation.

    Args:
        conversation_text: The original conversation text.
        previous_response: The malformed response from the first attempt.
        today_date: Today's date string, re-injected so relative dates still resolve.

    Returns:
        A retry user message that emphasises strict JSON output.
    """
    return (
        f"Your previous response was not valid JSON or used values outside the allowed enums.\n"
        f"Previous response: {previous_response[:300]}\n\n"
        f"Try again. Return ONLY valid JSON with the exact enum values specified. "
        f"No markdown, no explanation.\n"
        f"Remember:\n"
        f"  - scheduled_followup_date must be a string in 'DD Mon YYYY' format, or null if no date was committed.\n"
        f"  - scheduled_followup_time must ALWAYS be a string (never null) — use 'Not specified' if no time was mentioned.\n"
        f"  - client_pain_points and client_recommendations must be JSON arrays (use [] if empty) — never omit them.\n\n"
        f"Today's date: {today_date}\n"
        f"Conversation:\n{conversation_text.strip()}"
    )


def build_analysis_prompt_with_history(
    conversation_text: str,
    today_date: str,
    history: list[dict],
) -> str:
    """
    Builds the user-turn message when past conversations exist for this lead.

    The AI receives a concise summary of each past interaction as background
    context, followed by the CURRENT conversation to analyse. This lets the
    model detect evolving intent, repeated concerns, or pattern changes across
    multiple touchpoints with the same lead.

    Args:
        conversation_text: The new conversation to analyse.
        today_date:        Today's date string, injected for relative-date resolution.
        history:           List of past conversation dicts from the database
                           (oldest first). Each dict has: bde_id, conversation_text,
                           analysis (dict), created_at.

    Returns:
        A formatted user message string ready to send to the LLM.
    """
    if not history:
        # No history — fall back to the standard prompt
        return build_analysis_prompt(conversation_text, today_date)

    # Build a compact summary of each past interaction
    history_lines = []
    for i, h in enumerate(history, 1):
        a    = h.get("analysis", {})
        date = h.get("created_at", "")[:10]  # just the YYYY-MM-DD portion
        pain = a.get("client_pain_points", [])
        recs = a.get("client_recommendations", [])
        text_snippet = h.get("conversation_text", "")[:150]
        if len(h.get("conversation_text", "")) > 150:
            text_snippet += "..."

        history_lines.append(
            f"[Interaction {i}]  Date: {date}  |  BDE: {h.get('bde_id', 'unknown')}\n"
            f"  Conversation snippet : {text_snippet}\n"
            f"  Stage / Priority     : {a.get('sales_stage')} / {a.get('priority')}\n"
            f"  Recommended action   : {a.get('recommended_action')}\n"
            f"  Motive (AI summary)  : {a.get('motive_summary', '')}\n"
            f"  Client pain points   : {pain}\n"
            f"  Client requests      : {recs}"
        )

    history_block = "\n\n".join(history_lines)

    return (
        f"Today's date: {today_date}\n\n"
        f"=== PAST CONVERSATION HISTORY FOR THIS LEAD ({len(history)} interaction(s)) ===\n"
        f"Use the history below as background context to better understand the lead's evolving\n"
        f"intent, unresolved concerns, and overall trajectory. Do NOT re-analyse past interactions.\n"
        f"Analyse ONLY the CURRENT CONVERSATION at the bottom.\n\n"
        f"{history_block}\n\n"
        f"=== CURRENT CONVERSATION — ANALYSE THIS ===\n"
        f"{conversation_text.strip()}"
    )

