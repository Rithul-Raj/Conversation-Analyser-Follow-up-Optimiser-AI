"""
Prompt builder for the free-form Q&A endpoint.

Design principle: one generic template handles ANY question a BDE might ask
about a conversation. No separate logic per question type — the LLM handles
interpretation based on context + question alone.
"""

QA_SYSTEM_PROMPT = """You are a sales-intelligence assistant. You will be given a sales conversation summary and a question from a Business Development Executive (BDE).

Your task: answer the question accurately and concisely based solely on the content of the conversation. 

Rules:
- Answer in plain text only — no JSON, no bullet lists unless the question specifically calls for it.
- Be direct and practical. The BDE needs actionable insight, not generic advice.
- If the conversation does not contain enough information to answer confidently, say so clearly instead of guessing.
- Keep your answer to 2–4 sentences unless the question requires more detail."""


def build_qa_prompt(conversation_text: str, question: str) -> str:
    """
    Builds the user-turn message for a free-form Q&A request.

    Args:
        conversation_text: The raw conversation summary pasted by the BDE.
        question: Any arbitrary question the BDE wants answered about this conversation.

    Returns:
        The formatted user message to send to the LLM.
    """
    return (
        f"Conversation summary:\n{conversation_text.strip()}\n\n"
        f"Question: {question.strip()}"
    )
