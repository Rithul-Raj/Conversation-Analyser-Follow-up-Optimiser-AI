"""
FastAPI application — entry point.

Endpoints:
  POST /analyze-conversation       — structured sales analysis (AI)
  POST /ask-conversation           — free-form Q&A about any conversation (AI)
  POST /reminder-status            — compute reminder countdown for one lead (pure Python)
  POST /notifications/by-date      — find all leads scheduled for a specific date/time
  POST /notifications/daily        — today's urgent leads (OVERDUE / TODAY / TOMORROW)
  POST /notifications/client       — find follow-ups for a specific client

Rate-limit errors from Gemini are caught here and returned as HTTP 429.
All other unexpected errors return HTTP 500 with a safe message.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env before anything else so GEMINI_API_KEY is available to all modules.
load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Ensure local packages resolve correctly when running from project root.
sys.path.insert(0, os.path.dirname(__file__))

from schemas.conversation_analysis import ConversationAnalysisResponse, Reminder
from services.database import (
    get_all_leads, get_conversations_by_date,
    get_lead_history, init_db, save_conversation,
)
from services.followup_rules import get_follow_up_days
from services.llm_client import RateLimitError, analyze_conversation, ask_question
from services.reminder_service import compute_reminder
from services.notification_service import filter_by_date, get_daily_summary, find_by_client
from services.utils import normalize_bde_id, normalize_date_input, normalize_lead_id

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    """Initialise the SQLite database at startup."""
    init_db()
    logger.info("Database initialised.")
    yield


app = FastAPI(
    title="Conversation Intelligence AI",
    description=(
        "LLM-powered system that analyses sales conversation summaries and "
        "returns structured recommendations for BDEs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,    # Swagger UI disabled — use cli.py for interactive use
    redoc_url=None,
)

# Allow all origins for local development. Lock this down in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    lead_id: str = Field(
        ...,
        description="Unique identifier for the lead (e.g. 'LEAD-001', CRM ID).",
        examples=["LEAD-001"],
    )
    bde_id: str = Field(
        ...,
        description="Employee ID of the BDE handling this conversation.",
        examples=["EMP-042"],
    )
    conversation_text: str = Field(
        ...,
        min_length=20,
        description="Full conversation summary pasted by the BDE after a client call.",
        examples=["Client called asking about our enterprise pricing..."],
    )

    @field_validator("conversation_text", mode="after")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("conversation_text must not be blank or whitespace-only.")
        return v


class AskRequest(BaseModel):
    conversation_text: str = Field(
        ...,
        min_length=20,
        description="Full conversation summary pasted by the BDE.",
    )
    question: str = Field(
        ...,
        min_length=5,
        description="Any free-form question about the conversation.",
        examples=["Is the client price-sensitive or feature-sensitive?"],
    )

    @field_validator("conversation_text", "question", mode="after")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank or whitespace-only.")
        return v


class AskResponse(BaseModel):
    answer: str = Field(..., description="Plain-text answer from the AI.")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RateLimitError)
async def rate_limit_handler(request: Request, exc: RateLimitError):
    logger.warning("Gemini rate limit hit.")
    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                "The AI service rate limit has been reached. "
                "Please wait a moment and try again."
            )
        },
    )


@app.exception_handler(EnvironmentError)
async def env_error_handler(request: Request, exc: EnvironmentError):
    logger.error("Server configuration error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Server configuration error: GEMINI_API_KEY is not set. "
                      "Contact the server administrator."
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Utility"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "conversation-intelligence-ai"}


# ---------------------------------------------------------------------------
# Endpoint 1: Structured conversation analysis
# ---------------------------------------------------------------------------
@app.post(
    "/analyze-conversation",
    response_model=ConversationAnalysisResponse,
    tags=["Analysis"],
    summary="Analyse a sales conversation and return structured recommendations.",
)
def analyze_conversation_endpoint(request: AnalyzeRequest):
    """
    Accepts a lead_id, bde_id, and sales conversation summary. Returns:
    - Current sales stage, priority, recommended action
    - Conversation mode and motive summary
    - Extracted follow-up date and time
    - Client pain points and recommendations
    - Reminder countdown block
    - Follow-up days (derived from priority)
    - conversation_id (DB row ID for this saved conversation)
    - history_used (how many past conversations informed this analysis)

    Past conversations for the same lead_id are automatically fetched and
    injected as context so the AI can account for evolving intent.
    Retries once if the LLM returns an invalid/malformed response.

    Note: defined as a plain `def` (not async) so FastAPI runs it in a
    thread-pool worker and the event loop is never blocked by the
    synchronous Gemini and SQLite calls.
    """
    logger.info(
        "Received /analyze-conversation  lead_id=%s  bde_id=%s  (%d chars).",
        request.lead_id, request.bde_id, len(request.conversation_text),
    )

    # Normalize IDs so LEAD001, lead-001, LEAD-001 all resolve to the same record
    lead_id = normalize_lead_id(request.lead_id)
    bde_id  = normalize_bde_id(request.bde_id)

    # Reject IDs that normalize to an empty string (e.g. "###" or purely symbolic)
    if not lead_id or not bde_id:
        raise HTTPException(
            status_code=422,
            detail="lead_id and bde_id must contain at least one alphanumeric character.",
        )

    # 1. Fetch past conversations for this lead (up to 5, oldest first)
    history = get_lead_history(lead_id, limit=5)
    logger.info("History fetched: %d past conversation(s) for lead '%s'.", len(history), lead_id)

    # 2. Call AI with history-aware prompt
    try:
        llm_output = analyze_conversation(request.conversation_text, history=history)
    except RateLimitError:
        raise
    except EnvironmentError:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract valid analysis from AI response: {exc}",
        )
    except RuntimeError as exc:
        logger.error("LLM call failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while calling the AI service.",
        )

    # 3. Deterministic derived fields — no AI involved
    follow_up_days = get_follow_up_days(llm_output.priority)
    reminder_result = compute_reminder(
        llm_output.scheduled_followup_date,
        llm_output.scheduled_followup_time,
    )
    reminder = Reminder(
        status=reminder_result.status,
        days_remaining=reminder_result.days_remaining,
        reminder_message=reminder_result.reminder_message,
    )

    # 4. Save conversation + analysis to DB
    analysis_dict = llm_output.model_dump()
    conversation_id = save_conversation(
        lead_id=lead_id,
        bde_id=bde_id,
        conversation_text=request.conversation_text,
        analysis=analysis_dict,
    )
    logger.info("Conversation saved: id=%d  lead=%s.", conversation_id, lead_id)

    # 5. Return full response
    return ConversationAnalysisResponse(
        **llm_output.model_dump(),
        follow_up_days=follow_up_days,
        reminder=reminder,
        lead_id=lead_id,
        bde_id=bde_id,
        conversation_id=conversation_id,
        history_used=len(history),
    )


# ---------------------------------------------------------------------------
# Lead history endpoints (pure Python, no AI)
# ---------------------------------------------------------------------------
@app.get(
    "/leads",
    tags=["Lead History"],
    summary="List all leads that have at least one stored conversation.",
)
async def list_leads():
    """
    Returns a list of all unique lead IDs with total interaction count
    and timestamp of the most recent conversation.
    """
    return get_all_leads()


@app.get(
    "/leads/due-today",
    tags=["Lead History"],
    summary="Get all leads whose latest scheduled follow-up date is today.",
)
async def leads_due_today():
    """
    Pure Python — no AI, no API cost, instant response.

    Returns all leads whose LATEST stored conversation has a
    scheduled_followup_date matching today's date. Results include
    the full analysis block for each matching lead.

    Useful for the backend to display a daily dashboard of leads
    that need attention today.
    """
    from datetime import date as _date
    today_str = _date.today().strftime("%d %b %Y")
    results = get_conversations_by_date(today_str)
    return results


@app.get(
    "/leads/{lead_id}/history",
    tags=["Lead History"],
    summary="Get full conversation history for a specific lead.",
)
async def lead_history(
    lead_id: str,
    limit: int = Query(default=10, ge=1, le=100, description="Number of conversations to return (1-100)."),
):
    """
    Returns stored conversations for the given lead_id, newest first.
    Each item includes the original conversation text, the full AI analysis,
    and the BDE who handled it.
    """
    lead_id = normalize_lead_id(lead_id)
    history = get_lead_history(lead_id, limit=limit, newest_first=True)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No conversations found for lead '{lead_id}'.",
        )
    return history


# ---------------------------------------------------------------------------
# Endpoint 2: Reminder status check (pure Python, no AI)
# ---------------------------------------------------------------------------
class ReminderRequest(BaseModel):
    scheduled_followup_date: str | None = Field(
        None,
        description="Date string in 'DD Mon YYYY' format (e.g. '24 Sep 2026'). null = not scheduled.",
        examples=["24 Sep 2026"],
    )
    scheduled_followup_time: str = Field(
        "Not specified",
        description="Time string (e.g. '11:00 AM', '2:00 PM - 4:00 PM', 'Morning'). Optional.",
        examples=["11:00 AM"],
    )


class ReminderResponse(BaseModel):
    status:           str = Field(..., description="Reminder urgency status.")
    days_remaining:   int | None = Field(None, description="Days until follow-up (negative = overdue).")
    reminder_message: str = Field(..., description="Human-readable reminder message for the BDE.")


@app.post(
    "/reminder-status",
    response_model=ReminderResponse,
    tags=["Reminder"],
    summary="Check the reminder countdown for any scheduled follow-up date.",
)
async def reminder_status_endpoint(request: ReminderRequest):
    """
    Pure Python endpoint — no AI, no API cost, instant response.

    Given a scheduled_followup_date (from a previous /analyze-conversation response),
    returns the current reminder status so the BDE knows how urgent the follow-up is.

    Reminder statuses:
    - OVERDUE      : the scheduled date has already passed
    - TODAY        : follow up today
    - TOMORROW     : follow up tomorrow
    - THIS_WEEK    : within 2–7 days
    - UPCOMING     : more than 7 days away
    - NOT_SCHEDULED: no date was committed
    """
    result = compute_reminder(request.scheduled_followup_date, request.scheduled_followup_time)
    return ReminderResponse(**result.to_dict())


# ---------------------------------------------------------------------------
# Shared schema: ReminderEntry
# A single lead record submitted by the BDE for notification queries.
# NOTE: No database is connected yet. The BDE passes their own lead records
# in the request body. Future DB integration will remove this requirement.
# ---------------------------------------------------------------------------
class ReminderEntry(BaseModel):
    client_id:               str | None = Field(None,  description="Any unique identifier for the client (e.g. CRM ID, phone, email).")
    client_name:             str        = Field(...,   description="Full name of the client.", examples=["David Chen"])
    scheduled_followup_date: str | None = Field(None,  description="Date in 'DD Mon YYYY' format. Null if not scheduled.", examples=["24 Sep 2026"])
    scheduled_followup_time: str        = Field("Not specified", description="Time string or 'Not specified'.", examples=["11:00 AM"])
    notes:                   str | None = Field(None,  description="Optional context about the lead or meeting.")


class NotificationResult(BaseModel):
    client_id:               str | None
    client_name:             str
    scheduled_followup_date: str | None
    scheduled_followup_time: str
    notes:                   str | None
    reminder:                dict = Field(..., description="Computed reminder block (status, days_remaining, reminder_message).")


# ---------------------------------------------------------------------------
# Endpoint: Find leads by date (and optional time)
# ---------------------------------------------------------------------------
class ByDateRequest(BaseModel):
    date: str = Field(
        ...,
        description="Date to search for in 'DD Mon YYYY' format.",
        examples=["24 Sep 2026"],
    )
    time: str | None = Field(
        None,
        description="Optional time filter. If provided, only entries whose time contains this string are returned.",
        examples=["11:00 AM"],
    )
    entries: list[ReminderEntry] = Field(
        ...,
        description="Your list of lead records to search through.",
    )


@app.post(
    "/notifications/by-date",
    response_model=list[NotificationResult],
    tags=["Notifications"],
    summary="Find all scheduled leads for a specific date (time optional).",
)
async def notifications_by_date(request: ByDateRequest):
    """
    Pure Python — no AI, no API cost, instant.

    Submit your list of lead entries and a target date. Returns all leads
    whose scheduled_followup_date matches, sorted by urgency (OVERDUE first).
    Optionally filter by time as well.

    **Future integration note:** Once a database is connected, the `entries`
    field will be removed and the system will query the DB automatically.
    """
    raw = [e.model_dump() for e in request.entries]
    results = filter_by_date(raw, request.date, request.time)
    return results


# ---------------------------------------------------------------------------
# Endpoint: Daily summary (OVERDUE + TODAY + TOMORROW)
# ---------------------------------------------------------------------------
class DailyRequest(BaseModel):
    entries: list[ReminderEntry] = Field(
        ...,
        description="Your full list of lead records.",
    )


@app.post(
    "/notifications/daily",
    response_model=list[NotificationResult],
    tags=["Notifications"],
    summary="Get today's urgent follow-ups: OVERDUE, TODAY, and TOMORROW leads.",
)
async def notifications_daily(request: DailyRequest):
    """
    Pure Python — no AI, no API cost, instant.

    Submit your full lead list. Returns only the urgent leads
    (OVERDUE, TODAY, TOMORROW) sorted by urgency — ideal for a
    morning check to know exactly which clients need immediate attention.

    **Future integration note:** Once a database is connected, the `entries`
    field will be removed and the system will query all leads from the DB.
    """
    raw = [e.model_dump() for e in request.entries]
    results = get_daily_summary(raw)
    return results


# ---------------------------------------------------------------------------
# Endpoint: Client-specific follow-up lookup
# ---------------------------------------------------------------------------
class ClientRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Client name, ID, or any partial string to search for (case-insensitive).",
        examples=["David", "david.chen@corp.com", "CRM-0042"],
    )
    entries: list[ReminderEntry] = Field(
        ...,
        description="Your list of lead records to search through.",
    )


@app.post(
    "/notifications/client",
    response_model=list[NotificationResult],
    tags=["Notifications"],
    summary="Find all scheduled follow-ups for a specific client.",
)
async def notifications_client(request: ClientRequest):
    """
    Pure Python — no AI, no API cost, instant.

    Search your lead list by client name or ID (case-insensitive, partial
    match supported). Returns all matching entries with live reminder status
    and days remaining — so the BDE can see at a glance where a specific
    client stands.

    **Future integration note:** Once a database is connected, the `entries`
    field will be removed and the system will query the DB by client identifier.
    """
    raw = [e.model_dump() for e in request.entries]
    results = find_by_client(raw, request.identifier)
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No leads found matching '{request.identifier}'.",
        )
    return results


@app.post(
    "/ask-conversation",
    response_model=AskResponse,
    tags=["Q&A"],
    summary="Ask any free-form question about a sales conversation.",
)
def ask_conversation_endpoint(request: AskRequest):
    """
    Accepts a conversation summary and ANY question the BDE wants to ask,
    and returns a plain-text answer.

    Defined as plain `def` so the synchronous Gemini call runs in a
    thread-pool worker and does not block the event loop.
    """
    logger.info(
        "Received /ask-conversation request (%d chars, question: %s).",
        len(request.conversation_text),
        request.question[:80],
    )

    try:
        answer = ask_question(request.conversation_text, request.question)
    except RateLimitError:
        raise  # handled by the exception handler above
    except EnvironmentError:
        raise
    except RuntimeError as exc:
        logger.error("LLM call failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while calling the AI service.",
        )

    return AskResponse(answer=answer)
