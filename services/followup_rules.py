"""
Deterministic follow-up day rules.

This is plain Python — no AI involved.
The LLM returns a priority; this module converts it to a concrete day count.
"""

from schemas.conversation_analysis import Priority

# Business rule: fixed mapping, not AI-derived.
FOLLOW_UP_DAYS: dict[str, int] = {
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 5,
}


def get_follow_up_days(priority: Priority) -> int:
    """
    Returns the number of days before the next follow-up based on priority.

    Args:
        priority: The Priority enum value returned by the LLM (already validated).

    Returns:
        An integer representing days until follow-up.

    Raises:
        KeyError: Should never occur in practice since priority is validated
                  by Pydantic before this function is called.
    """
    return FOLLOW_UP_DAYS[priority]
