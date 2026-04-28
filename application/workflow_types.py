"""Enums for workflow control-flow fields in TravelState."""

from enum import Enum


class WorkflowStep(str, Enum):
    PROFILE_LOADED = "profile_loaded"
    INTAKE_COMPLETE = "intake_complete"
    INTAKE_ERROR = "intake_error"
    OUT_OF_DOMAIN = "out_of_domain"
    RESEARCH_COMPLETE = "research_complete"
    BUDGET_DONE = "budget_done"
    AWAITING_REVIEW = "awaiting_review"
    APPROVAL_RECEIVED = "approval_received"
    REVISING_PLAN = "revising_plan"
    ATTRACTIONS_COMPLETE = "attractions_complete"
    FINALISED = "finalised"
    DONE = "done"


class FeedbackType(str, Enum):
    REVISE_PLAN = "revise_plan"
    CANCEL = "cancel"
    REWRITE_ITINERARY = "rewrite_itinerary"
