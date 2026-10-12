"""
Gemini API client with retry logic and schema validation.

Responsibilities:
  1. Call the Gemini API with a system + user prompt.
  2. Parse and validate the JSON response against the Pydantic schema.
  3. Retry exactly once if the response is malformed or contains invalid enum values.
  4. Raise a clear exception if both attempts fail — never return bad data silently.
  5. Handle Gemini rate-limit errors (429) gracefully.
"""

import json
import logging
import os
from datetime import date
from functools import lru_cache

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from prompts.analysis_prompt import (
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt_with_history,
    build_retry_prompt,
)
from prompts.qa_prompt import QA_SYSTEM_PROMPT, build_qa_prompt
from schemas.conversation_analysis import LLMAnalysisOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level Gemini configuration — runs once at import time.
# ---------------------------------------------------------------------------
_api_key    = os.getenv("GEMINI_API_KEY", "")
_model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

if _api_key:
    genai.configure(api_key=_api_key)


@lru_cache(maxsize=2)  # one entry per unique system prompt (analysis + Q&A)
def _get_model(system_instruction: str) -> genai.GenerativeModel:
    """
    Return a cached GenerativeModel for the given system instruction.
    lru_cache ensures we only ever create at most 4 distinct model objects
    (one per unique system prompt) — never recreating them on each request.
    """
    if not _api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    return genai.GenerativeModel(
        model_name=_model_name,
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(temperature=0.2),
    )


def _call_gemini(model: genai.GenerativeModel, user_message: str) -> str:
    """
    Send a single user message to Gemini and return the raw text response.

    Raises:
        ResourceExhausted: Propagated as-is — caught upstream and converted to
                           a user-friendly HTTP 429 response.
        RuntimeError: For any other unexpected Gemini error.
    """
    try:
        response = model.generate_content(user_message)
        return response.text.strip()
    except ResourceExhausted:
        raise  # handled in the route handler
    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc


def _parse_llm_json(raw_text: str) -> dict:
    """
    Extract and parse JSON from the LLM response.
    Handles the common case where the model wraps JSON in markdown fences
    despite being told not to.
    """
    text = raw_text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence line and closing fence line
        inner = [
            line for line in lines[1:]
            if not line.strip().startswith("```")
        ]
        text = "\n".join(inner).strip()
    return json.loads(text)


def analyze_conversation(
    conversation_text: str,
    history: list[dict] | None = None,
) -> LLMAnalysisOutput:
    """
    Send conversation text to Gemini and return a validated LLMAnalysisOutput.

    When `history` is provided (non-empty list of past conversation dicts from
    the database), the prompt includes a compact summary of those interactions
    as context so the AI can account for the lead's evolving intent.

    Strategy:
      - Attempt 1: standard (or history-aware) analysis prompt.
      - Attempt 2 (only if attempt 1 fails validation): retry prompt that
        references the invalid response and re-emphasises constraints.
      - If both fail: raise ValueError with a clear message.

    Args:
        conversation_text: The raw conversation summary from the BDE.
        history:           Optional list of past conversations for this lead
                           (oldest first), as returned by get_lead_history().

    Returns:
        A validated LLMAnalysisOutput instance.

    Raises:
        ResourceExhausted: Gemini rate limit hit.
        ValueError: Both attempts produced invalid responses.
        RuntimeError: Unexpected Gemini API failure.
    """
    model      = _get_model(ANALYSIS_SYSTEM_PROMPT)
    today_date = date.today().strftime("%d %b %Y")

    # Use history-aware prompt if past conversations exist
    user_message = build_analysis_prompt_with_history(
        conversation_text, today_date, history or []
    )

    for attempt in range(1, 3):  # max 2 attempts
        raw = _call_gemini(model, user_message)
        logger.debug("Gemini raw response (attempt %d): %s", attempt, raw[:500])

        try:
            data   = _parse_llm_json(raw)
            result = LLMAnalysisOutput.model_validate(data)
            logger.info("LLM response validated successfully on attempt %d.", attempt)
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Attempt %d validation failed: %s. Raw response: %s",
                attempt, exc, raw[:300],
            )
            if attempt == 1:
                # Retry with a corrective prompt (no history — keep it short)
                user_message = build_retry_prompt(conversation_text, raw, today_date)
            else:
                raise ValueError(
                    f"LLM returned invalid data on both attempts. "
                    f"Last raw response: {raw[:300]}"
                ) from exc

    # Unreachable, but satisfies type checkers
    raise ValueError("analyze_conversation: exhausted all retry attempts.")


def ask_question(conversation_text: str, question: str) -> str:
    """
    Answer any free-form question about a conversation using Gemini.

    This is a single, non-retried LLM call. Schema validation is not required
    because the output is plain text, not a structured object.

    Args:
        conversation_text: The raw conversation summary from the BDE.
        question: Any arbitrary question the BDE wants answered.

    Returns:
        A plain-text answer from the LLM.

    Raises:
        ResourceExhausted: Gemini rate limit hit.
        RuntimeError: Unexpected Gemini API failure.
    """
    model = _get_model(QA_SYSTEM_PROMPT)
    user_message = build_qa_prompt(conversation_text, question)
    return _call_gemini(model, user_message)
