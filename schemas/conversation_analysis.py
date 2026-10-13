"""
Pydantic models for the fixed output schema.

These enums define the ONLY valid values accepted from the LLM.
Any value outside these enums is rejected and triggers a retry.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class SalesStage(str, Enum):
    AWARENESS = "AWARENESS"
    INTEREST = "INTEREST"
    EVALUATION = "EVALUATION"
    NEGOTIATION = "NEGOTIATION"
    DECISION = "DECISION"
    CLOSED = "CLOSED"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecommendedAction(str, Enum):
    EXPLAIN_PRODUCT = "EXPLAIN_PRODUCT"
    SEND_QUOTATION = "SEND_QUOTATION"
    SEND_EMAIL = "SEND_EMAIL"
    SCHEDULE_MEETING = "SCHEDULE_MEETING"
    SCHEDULE_DEMO = "SCHEDULE_DEMO"
    CALL_CLIENT = "CALL_CLIENT"
    ANSWER_OBJECTION = "ANSWER_OBJECTION"
    SEND_DOCUMENTATION = "SEND_DOCUMENTATION"
    FOLLOW_UP = "FOLLOW_UP"
    ESCALATE_TECHNICAL = "ESCALATE_TECHNICAL"
    WAIT = "WAIT"
    CLOSE_LEAD = "CLOSE_LEAD"


class ConversationMode(str, Enum):
    PROFESSIONAL = "PROFESSIONAL"
    CASUAL = "CASUAL"
    TECHNICAL = "TECHNICAL"


class ReminderStatus(str, Enum):
    OVERDUE       = "OVERDUE"        # scheduled date has already passed
    TODAY         = "TODAY"          # follow-up is today
    TOMORROW      = "TOMORROW"       # follow-up is tomorrow
    THIS_WEEK     = "THIS_WEEK"      # within 2–7 days
    UPCOMING      = "UPCOMING"       # more than 7 days away
    NOT_SCHEDULED = "NOT_SCHEDULED"  # no date was committed in the conversation


class Reminder(BaseModel):
    """Computed reminder block — pure Python, no AI involved."""

    status: ReminderStatus = Field(
        ...,
        description=(
            "OVERDUE: date passed | TODAY: follow up today | TOMORROW: tomorrow | "
            "THIS_WEEK: within 7 days | UPCOMING: more than 7 days away | "
            "NOT_SCHEDULED: no date committed"
        ),
    )
    days_remaining: Optional[int] = Field(
        None,
        description="Days until the scheduled follow-up (negative = overdue). null if not scheduled.",
    )
    reminder_message: str = Field(
        ...,
        description="Human-readable reminder message for the BDE.",
    )


class LLMAnalysisOutput(BaseModel):
    """
    The raw structured response expected directly from the LLM.
    follow_up_days is NOT included here — it is derived via a plain Python
    lookup after validation, never predicted by the AI.
    """

    sales_stage: SalesStage = Field(
        ..., description="Current sales stage of the lead"
    )
    priority: Priority = Field(
        ..., description="Follow-up priority level"
    )
    recommended_action: RecommendedAction = Field(
        ..., description="Next recommended sales action"
    )
    conversation_mode: ConversationMode = Field(
        ..., description="Tone/mode of the conversation"
    )
    motive_summary: str = Field(
        ..., description="One sentence describing the real intent behind the conversation"
    )
    scheduled_followup_date: str | None = Field(
        None,
        description=(
            "Concrete calendar date for the next client touchpoint, extracted or calculated "
            "from an explicit commitment in the conversation (e.g. '24 Sep 2026'). "
            "null if the conversation contains no specific date or time commitment."
        ),
    )
    scheduled_followup_time: str = Field(
        "Not specified",
        description=(
            "Time of the next client touchpoint. Always a string, never null. "
            "Exact: '11:00 AM' | Range: '11:00 AM - 3:00 PM' | "
            "Vague: 'Morning' / 'Afternoon' / 'Evening' / 'Night' | "
            "No time mentioned: 'Not specified'."
        ),
    )
    client_pain_points: List[str] = Field(
        default_factory=list,
        description=(
            "Problems or frustrations the CLIENT explicitly stated in the conversation. "
            "Only include what was clearly said — never infer. Empty list if none."
        ),
    )
    client_recommendations: List[str] = Field(
        default_factory=list,
        description=(
            "Suggestions or requests the CLIENT made (not the BDE's suggestions to them). "
            "Only explicit client statements. Empty list if none."
        ),
    )

    @field_validator("scheduled_followup_date", mode="before")
    @classmethod
    def normalise_date_format(cls, v: object) -> str | None:
        """
        Normalise the AI-returned date to 'DD Mon YYYY' format.

        The prompt asks for 'DD Mon YYYY', but the AI occasionally returns
        other formats (e.g. '20 October 2026', '2026-10-20', 'Oct 20, 2026').
        This validator converts any recognised format so downstream code
        (date search, reminder computation) always sees the canonical form.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        for fmt in (
            "%d %b %Y",      # 20 Oct 2026   (canonical)
            "%d %B %Y",      # 20 October 2026
            "%Y-%m-%d",      # 2026-10-20
            "%B %d, %Y",     # October 20, 2026
            "%d/%m/%Y",      # 20/10/2026
            "%m/%d/%Y",      # 10/20/2026
        ):
            try:
                return datetime.strptime(v.strip(), fmt).strftime("%d %b %Y")
            except ValueError:
                continue
        return v  # return as-is; schema enforcement will handle the rest

    @field_validator("client_pain_points", "client_recommendations")
    @classmethod
    def check_item_length(cls, v: List[str]) -> List[str]:
        """Silently drop any item exceeding 15 words (matches the prompt specification)."""
        return [item for item in v if len(item.split()) <= 15]


class ConversationAnalysisResponse(LLMAnalysisOutput):
    """
    Final API response — extends LLMAnalysisOutput with deterministic fields
    computed via plain Python lookups (no AI involved).
    """

    follow_up_days: int = Field(
        ..., description="Days until follow-up, derived from priority (not AI-predicted)"
    )
    scheduled_followup_date: Optional[str] = Field(
        None,
        description=(
            "Concrete calendar date for the next client touchpoint, extracted or calculated "
            "from an explicit commitment in the conversation (e.g. '24 Sep 2026'). "
            "null if the conversation contains no specific date or time commitment."
        ),
    )
    scheduled_followup_time: str = Field(
        "Not specified",
        description=(
            "Time of the next client touchpoint. Always a string, never null. "
            "Exact: '11:00 AM' | Range: '11:00 AM - 3:00 PM' | "
            "Vague: 'Morning' / 'Afternoon' / 'Evening' / 'Night' | "
            "No time mentioned: 'Not specified'."
        ),
    )
    reminder: Reminder = Field(
        ...,
        description="Computed reminder block. Zero AI cost — derived from scheduled_followup_date.",
    )
    # --- Lead / BDE identity ---
    lead_id: str = Field(
        ..., description="Unique identifier for the lead this conversation belongs to."
    )
    bde_id: str = Field(
        ..., description="Employee ID of the BDE who handled this conversation."
    )
    conversation_id: int = Field(
        ..., description="Auto-generated DB ID for this saved conversation."
    )
    history_used: int = Field(
        ..., description="Number of past conversations included as context for this analysis."
    )

