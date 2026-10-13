"""
Gemini API client — uses the google-genai SDK (google-genai 2.x).

Responsibilities:
  1. Call the Gemini API with a system + user prompt.
  2. Parse and validate the JSON response against the Pydantic schema.
  3. Retry exactly once if the response is malformed or contains invalid enum values.
  4. Raise a clear exception if both attempts fail — never return bad data silently.
  5. Surface rate-limit errors as RateLimitError so main.py can return HTTP 429.
  6. Raise MissingAPIKeyError (not EnvironmentError) when GEMINI_API_KEY is absent.
"""

import json
import logging
import os
from functools import lru_cache

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from prompts.analysis_prompt import (
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt_with_history,
    build_retry_prompt,
)
from prompts.qa_prompt import QA_SYSTEM_PROMPT, build_qa_prompt
from schemas.conversation_analysis import LLMAnalysisOutput
from services.utils import get_today

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class MissingAPIKeyError(Exception):
    """Raised when GEMINI_API_KEY is not set in the environment."""


class RateLimitError(Exception):
    """Raised when the Gemini API returns HTTP 429."""


# ---------------------------------------------------------------------------
# Module-level config
# ---------------------------------------------------------------------------
_api_key    = os.getenv("GEMINI_API_KEY", "")
_model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    """
    Return a cached Gemini client.
    Raises MissingAPIKeyError immediately if the API key is not set.
    """
    if not _api_key:
        raise MissingAPIKeyError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the server."
        )
    return genai.Client(api_key=_api_key)


def _call_gemini(system_instruction: str, user_message: str) -> str:
    """
    Send a single user message to Gemini and return the raw text response.

    Raises:
        MissingAPIKeyError : GEMINI_API_KEY not configured.
        RateLimitError     : Gemini returned HTTP 429.
        RuntimeError       : Any other Gemini API error (includes HTTP status code).
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
    except MissingAPIKeyError:
        raise
    except genai_errors.APIError as exc:
        # APIError has a `.status` attribute with the HTTP status code (int)
        status = getattr(exc, "status", None)
        if status == 429:
            raise RateLimitError(
                "The Gemini API rate limit has been reached. Please wait and try again."
            ) from exc
        # Other API errors: include status code in the message for traceability
        msg = getattr(exc, "message", str(exc))
        raise RuntimeError(f"Gemini API error {status}: {msg}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unexpected Gemini client error: {exc}") from exc


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
      - Attempt 2: retry prompt that includes the invalid response.
      - If both fail: raise ValueError.

    Args:
        conversation_text: The raw conversation summary from the BDE.
        history:           Optional list of past conversations for this lead
                           (oldest first), as returned by get_lead_history().

    Raises:
        MissingAPIKeyError : API key not configured.
        RateLimitError     : Gemini rate limit hit.
        ValueError         : Both attempts produced invalid responses.
        RuntimeError       : Unexpected Gemini API failure.
    """
    today_date = get_today().strftime("%d %b %Y")

    user_message = build_analysis_prompt_with_history(
        conversation_text, today_date, history or []
    )

    for attempt in range(1, 3):
        raw = _call_gemini(ANALYSIS_SYSTEM_PROMPT, user_message)
        logger.debug("Gemini raw response (attempt %d): %s", attempt, raw[:500])

        try:
            data   = _parse_llm_json(raw)
            result = LLMAnalysisOutput.model_validate(data)
            logger.info("LLM response validated on attempt %d.", attempt)
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Attempt %d validation failed: %s. Raw snippet: %s",
                attempt, exc, raw[:200],
            )
            if attempt == 1:
                user_message = build_retry_prompt(conversation_text, raw, today_date)
            else:
                raise ValueError(
                    "The AI returned an unexpected response on both attempts. "
                    "Please try again."
                ) from exc

    raise ValueError("analyze_conversation: exhausted all retry attempts.")


def ask_question(conversation_text: str, question: str) -> str:
    """
    Answer any free-form question about a conversation using Gemini.

    Raises:
        MissingAPIKeyError : API key not configured.
        RateLimitError     : Gemini rate limit hit.
        RuntimeError       : Unexpected Gemini API failure.
    """
    user_message = build_qa_prompt(conversation_text, question)
    return _call_gemini(QA_SYSTEM_PROMPT, user_message)
