from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime
from app.core.constants import Decision, ApproverRole


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class ImpactedOnApproval(BaseModel):
    resultId:  Optional[str] = None
    requestId: Optional[str] = None
    itemCode:  str
    menuName:  str
    ruleField: Optional[str] = None


# ── Request / Response models ─────────────────────────────────────────────────

class OverrideApprovalCreate(BaseModel):
    """
    Payload submitted by approver.
    Fields injected by backend:
      approvalId, restaurantId, approvedBy, approvedByRole,
      decidedAt, isActive, createdAt
    Fields carried from override_request:
      effectiveFrom, effectiveTo, impactedOn, oldValue, newValue
    """
    overrideRequestId: str
    decision:          Decision
    decisionNotes:     str = Field(..., min_length=1)


class OverrideApprovalResponse(BaseModel):
    id:                  Optional[str]      = Field(None, alias="_id")
    approvalId:          str
    overrideRequestId:   str
    restaurantId:        str
    approvedBy:          str
    approvedByRole:      str
    decision:            Decision
    decisionNotes:       str
    decidedAt:           datetime
    effectiveFrom:       Optional[datetime]  = None
    effectiveTo:         Optional[datetime]  = None
    impactedOn:          Optional[dict]      = None
    oldValue:            Optional[dict]      = None
    newValue:            Optional[dict]      = None
    ruleVersionCreated:  Optional[str]       = None
    isActive:            bool                = False
    createdAt:           Optional[datetime]  = None

    class Config:
        populate_by_name = True
