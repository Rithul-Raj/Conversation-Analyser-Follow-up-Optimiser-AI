"""
Gemini API client — uses the google-genai SDK (replaces google-generativeai).

Responsibilities:
  1. Call the Gemini API with a system + user prompt.
  2. Parse and validate the JSON response against the Pydantic schema.
  3. Retry exactly once if the response is malformed or contains invalid enum values.
  4. Raise a clear exception if both attempts fail — never return bad data silently.
  5. Surface rate-limit errors as RateLimitError so main.py can return HTTP 429.
  6. Raise EnvironmentError early (with a clear message) if the API key is missing.
"""

import json
import logging
import os
from datetime import date
from functools import lru_cache

from google import genai
from google.genai import types

from prompts.analysis_prompt import (
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt_with_history,
    build_retry_prompt,
)
from prompts.qa_prompt import QA_SYSTEM_PROMPT, build_qa_prompt
from schemas.conversation_analysis import LLMAnalysisOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception — raised when Gemini returns HTTP 429
# ---------------------------------------------------------------------------
class RateLimitError(Exception):
    """Raised when the Gemini API rate limit is exceeded."""


# ---------------------------------------------------------------------------
# Module-level config — read once at import time
# ---------------------------------------------------------------------------
_api_key    = os.getenv("GEMINI_API_KEY", "")
_model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    """
    Return a cached Gemini client.
    Raises EnvironmentError immediately if the API key is not set,
    so the error surfaces at request time with a clear message.
    """
    if not _api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    return genai.Client(api_key=_api_key)


def _call_gemini(system_instruction: str, user_message: str) -> str:
    """
    Send a single user message to Gemini and return the raw text response.

    Raises:
        EnvironmentError   : API key not configured.
        RateLimitError     : Gemini returned HTTP 429.
        RuntimeError       : Any other Gemini error.
    """
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=_model_name,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            ),
        )
        return response.text.strip()
    except EnvironmentError:
        raise  # propagate missing-key error as-is
    except Exception as exc:
        # Detect rate limit by inspecting exception class name or message
        exc_type = type(exc).__name__
        exc_str  = str(exc)
        if "429" in exc_str or "quota" in exc_str.lower() or "rate" in exc_str.lower() or "ResourceExhausted" in exc_type:
            raise RateLimitError(
                "The Gemini API rate limit has been reached. Please wait and try again."
            ) from exc
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc


def _parse_llm_json(raw_text: str) -> dict:
    """
    Extract and parse JSON from the LLM response.
    Handles the common case where the model wraps JSON in markdown fences.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
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

    Strategy:
      - Attempt 1: standard (or history-aware) analysis prompt.
      - Attempt 2 (only if attempt 1 fails): retry prompt that includes the
        invalid response and re-emphasises constraints.
      - If both fail: raise ValueError with a clear message.

    Args:
        conversation_text: The raw conversation summary from the BDE.
        history:           Optional list of past conversations for this lead
                           (oldest first), as returned by get_lead_history().

    Returns:
        A validated LLMAnalysisOutput instance.

    Raises:
        EnvironmentError : API key not configured.
        RateLimitError   : Gemini rate limit hit.
        ValueError       : Both attempts produced invalid responses.
        RuntimeError     : Unexpected Gemini API failure.
    """
    today_date = date.today().strftime("%d %b %Y")

    user_message = build_analysis_prompt_with_history(
        conversation_text, today_date, history or []
    )

    for attempt in range(1, 3):   # max 2 attempts
        raw = _call_gemini(ANALYSIS_SYSTEM_PROMPT, user_message)
        logger.debug("Gemini raw response (attempt %d): %s", attempt, raw[:500])

        try:
            data   = _parse_llm_json(raw)
            result = LLMAnalysisOutput.model_validate(data)
            logger.info("LLM response validated successfully on attempt %d.", attempt)
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Attempt %d validation failed: %s. Raw: %s",
                attempt, exc, raw[:300],
            )
            if attempt == 1:
                user_message = build_retry_prompt(conversation_text, raw, today_date)
            else:
                raise ValueError(
                    f"LLM returned invalid data on both attempts. "
                    f"Last raw response: {raw[:300]}"
                ) from exc

    raise ValueError("analyze_conversation: exhausted all retry attempts.")


def ask_question(conversation_text: str, question: str) -> str:
    """
    Answer any free-form question about a conversation using Gemini.

    Single call — no retry needed because output is plain text, not a
    structured object.

    Raises:
        EnvironmentError : API key not configured.
        RateLimitError   : Gemini rate limit hit.
        RuntimeError     : Unexpected Gemini API failure.
    """
    user_message = build_qa_prompt(conversation_text, question)
    return _call_gemini(QA_SYSTEM_PROMPT, user_message)
