"""User feedback handling."""

from paperscout.feedback.profile import (
    FeedbackSummary,
    build_feedback_record,
    feedback_summary_lines,
    profile_from_feedback,
    select_recommendation_for_feedback,
    summarize_feedback,
)

__all__ = [
    "FeedbackSummary",
    "build_feedback_record",
    "feedback_summary_lines",
    "profile_from_feedback",
    "select_recommendation_for_feedback",
    "summarize_feedback",
]
