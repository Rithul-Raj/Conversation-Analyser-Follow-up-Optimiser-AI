"""
tests/test_api.py
-----------------
Offline pytest suite for all FastAPI endpoints.

- No live Gemini API key required.
- No running server required.
- All AI calls are mocked via unittest.mock.patch.
- Database calls are mocked to return in-memory fixtures.
- Uses FastAPI's TestClient (backed by httpx).

Usage:
    pytest tests/test_api.py -v
    pytest tests/test_api.py -v -k "test_analyze"  # run a single test
"""
import sys
sys.path.insert(0, ".")

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ─── Fixtures ──────────────────────────────────────────────────────────────

from schemas.conversation_analysis import (
    ConversationMode,
    LLMAnalysisOutput,
    Priority,
    RecommendedAction,
    SalesStage,
)

_TODAY = date.today().strftime("%d %b %Y")
_FUTURE = (date.today() + timedelta(days=8)).strftime("%d %b %Y")

MOCK_ANALYSIS = LLMAnalysisOutput(
    sales_stage=SalesStage.EVALUATION,
    priority=Priority.MEDIUM,
    recommended_action=RecommendedAction.SEND_DOCUMENTATION,
    conversation_mode=ConversationMode.PROFESSIONAL,
    motive_summary="The client wants a technical spec before deciding.",
    scheduled_followup_date=_FUTURE,
    scheduled_followup_time="11:00 AM",
    client_pain_points=["Current system is slow"],
    client_recommendations=["Requested detailed technical spec"],
)

MOCK_HISTORY = [
    {
        "id": 1,
        "lead_id": "LEAD-001",
        "bde_id": "EMP-042",
        "conversation_text": "First call with client.",
        "analysis": MOCK_ANALYSIS.model_dump(),
        "created_at": "2026-10-01T10:00:00+00:00",
    }
]

ANALYZE_PAYLOAD = {
    "lead_id": "LEAD-001",
    "bde_id": "EMP-042",
    "conversation_text": (
        "Client called to discuss integration. She mentioned their current "
        "CRM is too slow and wants a detailed technical spec. "
        "Follow-up scheduled for 20 Oct 2026 at 11 AM."
    ),
}

ASK_PAYLOAD = {
    "conversation_text": (
        "Client called to discuss integration. She mentioned their current "
        "CRM is too slow and wants a detailed technical spec."
    ),
    "question": "Is the client price-sensitive or feature-sensitive?",
}


# ─── App client (with all AI + DB mocked) ──────────────────────────────────

@pytest.fixture
def client():
    """
    Return a TestClient with:
      - analyze_conversation mocked (no Gemini call)
      - ask_question mocked (no Gemini call)
      - save_conversation mocked (no SQLite write)
      - get_lead_history mocked (returns empty list — no prior history)
      - get_all_leads mocked
    """
    with (
        patch("services.llm_client.analyze_conversation", return_value=MOCK_ANALYSIS),
        patch("services.llm_client.ask_question", return_value="The client is feature-sensitive."),
        patch("main.analyze_conversation", return_value=MOCK_ANALYSIS),
        patch("main.ask_question", return_value="The client is feature-sensitive."),
        patch("main.save_conversation", return_value=99),
        patch("main.get_lead_history", return_value=[]),
        patch("main.get_all_leads", return_value=[
            {"lead_id": "LEAD-001", "total_interactions": 1,
             "last_interaction": "2026-10-12T10:00:00+00:00"}
        ]),
    ):
        from main import app
        yield TestClient(app, raise_server_exceptions=False)


# ─── /health ───────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ─── /analyze-conversation ─────────────────────────────────────────────────

def test_analyze_returns_200(client):
    r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    assert r.status_code == 200


def test_analyze_response_has_required_fields(client):
    r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    d = r.json()
    for field in [
        "sales_stage", "priority", "recommended_action",
        "conversation_mode", "motive_summary",
        "scheduled_followup_date", "scheduled_followup_time",
        "follow_up_days", "reminder", "lead_id", "bde_id",
        "conversation_id", "history_used",
    ]:
        assert field in d, f"Missing field: {field}"


def test_analyze_lead_id_normalised(client):
    """'lead001' and 'LEAD-001' must both produce lead_id='LEAD-001'."""
    payload = {**ANALYZE_PAYLOAD, "lead_id": "lead001"}
    r = client.post("/analyze-conversation", json=payload)
    assert r.json()["lead_id"] == "LEAD-001"


def test_analyze_reminder_block_present(client):
    r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    rem = r.json().get("reminder", {})
    assert "status" in rem
    assert "days_remaining" in rem
    assert "reminder_message" in rem


def test_analyze_rejects_short_text(client):
    payload = {**ANALYZE_PAYLOAD, "conversation_text": "Too short"}
    r = client.post("/analyze-conversation", json=payload)
    assert r.status_code == 422


def test_analyze_rejects_whitespace_only(client):
    payload = {**ANALYZE_PAYLOAD, "conversation_text": "   " * 10}
    r = client.post("/analyze-conversation", json=payload)
    assert r.status_code == 422


def test_analyze_rejects_empty_lead_id(client):
    """An ID that normalises to empty string must be rejected."""
    payload = {**ANALYZE_PAYLOAD, "lead_id": "###"}
    r = client.post("/analyze-conversation", json=payload)
    assert r.status_code == 422


def test_analyze_rejects_missing_lead_id(client):
    payload = {"bde_id": "EMP-042", "conversation_text": ANALYZE_PAYLOAD["conversation_text"]}
    r = client.post("/analyze-conversation", json=payload)
    assert r.status_code == 422


# ─── /ask-conversation ─────────────────────────────────────────────────────

def test_ask_returns_200(client):
    r = client.post("/ask-conversation", json=ASK_PAYLOAD)
    assert r.status_code == 200
    assert "answer" in r.json()


def test_ask_rejects_short_question(client):
    payload = {**ASK_PAYLOAD, "question": "Ok"}
    r = client.post("/ask-conversation", json=payload)
    assert r.status_code == 422


def test_ask_rejects_whitespace_question(client):
    payload = {**ASK_PAYLOAD, "question": "     "}
    r = client.post("/ask-conversation", json=payload)
    assert r.status_code == 422


# ─── /leads ────────────────────────────────────────────────────────────────

def test_list_leads_returns_200(client):
    r = client.get("/leads")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ─── /leads/{id}/history ───────────────────────────────────────────────────

def test_lead_history_404_for_unknown_lead(client):
    with patch("main.get_lead_history", return_value=[]):
        r = client.get("/leads/UNKNOWN-999/history")
    assert r.status_code == 404


def test_lead_history_invalid_limit_rejected(client):
    r = client.get("/leads/LEAD-001/history?limit=0")
    assert r.status_code == 422


def test_lead_history_negative_limit_rejected(client):
    r = client.get("/leads/LEAD-001/history?limit=-1")
    assert r.status_code == 422


def test_lead_history_returns_data(client):
    with patch("main.get_lead_history", return_value=MOCK_HISTORY):
        r = client.get("/leads/LEAD-001/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert r.json()[0]["lead_id"] == "LEAD-001"


# ─── /reminder-status ──────────────────────────────────────────────────────

def test_reminder_today(client):
    payload = {"scheduled_followup_date": _TODAY, "scheduled_followup_time": "11:00 AM"}
    r = client.post("/reminder-status", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "TODAY"


def test_reminder_not_scheduled(client):
    payload = {"scheduled_followup_date": None, "scheduled_followup_time": "Not specified"}
    r = client.post("/reminder-status", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "NOT_SCHEDULED"


def test_reminder_upcoming(client):
    future = (date.today() + timedelta(days=10)).strftime("%d %b %Y")
    payload = {"scheduled_followup_date": future, "scheduled_followup_time": "Not specified"}
    r = client.post("/reminder-status", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "UPCOMING"


# ─── /leads/due-today ──────────────────────────────────────────────────────

def test_due_today_returns_list(client):
    with patch("main.get_conversations_by_date", return_value=[]):
        r = client.get("/leads/due-today")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ─── Date normalisation via schema ─────────────────────────────────────────

def test_date_format_normalisation():
    """AI returning 'October 20, 2026' must be normalised to '20 Oct 2026'."""
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "October 20, 2026"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date == "20 Oct 2026"


def test_date_iso_format_normalisation():
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "2026-10-20"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date == "20 Oct 2026"


def test_date_abbreviated_month_normalisation():
    """'Oct 20, 2026' must normalise to '20 Oct 2026'."""
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "Oct 20, 2026"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date == "20 Oct 2026"


def test_impossible_date_returns_none():
    """'31 Feb 2026' is an invalid date — schema must return None, not save garbage."""
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "31 Feb 2026"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date is None


def test_garbage_date_returns_none():
    """Non-date string 'banana' → None."""
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "banana"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date is None


def test_relative_date_returns_none():
    """Relative string 'tomorrow' → None (not parseable as absolute date)."""
    from schemas.conversation_analysis import LLMAnalysisOutput
    data = MOCK_ANALYSIS.model_dump()
    data["scheduled_followup_date"] = "tomorrow"
    obj = LLMAnalysisOutput.model_validate(data)
    assert obj.scheduled_followup_date is None


# ─── Error scenario tests ───────────────────────────────────────────────────

def test_analyze_429_rate_limit(client):
    """RateLimitError from AI layer must propagate as HTTP 429."""
    from services.llm_client import RateLimitError
    with patch("main.analyze_conversation", side_effect=RateLimitError("quota")):
        r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"].lower()


def test_analyze_502_ai_runtime_error(client):
    """RuntimeError from AI layer must return HTTP 502 (not 500)."""
    with patch("main.analyze_conversation", side_effect=RuntimeError("Gemini API error 503: overloaded")):
        r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    assert r.status_code == 502


def test_analyze_500_missing_api_key(client):
    """MissingAPIKeyError must return HTTP 500 with a clear message."""
    from services.llm_client import MissingAPIKeyError
    with patch("main.analyze_conversation", side_effect=MissingAPIKeyError("GEMINI_API_KEY not set")):
        r = client.post("/analyze-conversation", json=ANALYZE_PAYLOAD)
    assert r.status_code == 500
    assert "GEMINI_API_KEY" in r.json()["detail"]


def test_ask_429_rate_limit(client):
    """RateLimitError in /ask-conversation must propagate as HTTP 429."""
    from services.llm_client import RateLimitError
    with patch("main.ask_question", side_effect=RateLimitError("quota")):
        r = client.post("/ask-conversation", json=ASK_PAYLOAD)
    assert r.status_code == 429


def test_ask_502_ai_runtime_error(client):
    """RuntimeError in /ask-conversation must return HTTP 502."""
    with patch("main.ask_question", side_effect=RuntimeError("Gemini API error 503: overloaded")):
        r = client.post("/ask-conversation", json=ASK_PAYLOAD)
    assert r.status_code == 502


def test_swagger_ui_accessible(client):
    """Swagger UI must be accessible at /docs."""
    r = client.get("/docs")
    assert r.status_code == 200
