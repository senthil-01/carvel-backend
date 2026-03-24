from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime
from enum import Enum
from app.core.constants import (
    OverrideType, OverrideReason, OverrideStatus, RequestorRole
)


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class ImpactedOn(BaseModel):
    type:      str                  # calculation or rule
    resultId:  Optional[str] = None # links to calculation_results
    requestId: Optional[str] = None # links to calculation_requests
    itemCode:  str
    menuName:  str
    ruleField: Optional[str] = None # rule override only — e.g. servesPerTray


# ── Request / Response models ─────────────────────────────────────────────────

class OverrideRequestCreate(BaseModel):
    """
    Payload raised by sales_rep / catering_manager / operations_manager.
    Fields injected by backend:
      overrideRequestId, restaurantId, requestedBy, requestedByRole,
      requestedDate, status, createdAt, updatedAt
    """
    overrideType:       OverrideType
    impactedOn:         ImpactedOn
    oldValue:           dict                   # current value before override
    newValue:           dict                   # requested new value
    reason:             OverrideReason
    justificationNotes: str = Field(..., min_length=20)
    effectiveFrom:      datetime
    effectiveTo:        Optional[datetime] = None   # null = permanent


    @model_validator(mode="after")
    def validate_values(self):
        if self.newValue == self.oldValue:
            raise ValueError("newValue must differ from oldValue")
        return self


class OverrideRequestResponse(BaseModel):
    id:                 Optional[str]      = Field(None, alias="_id")
    overrideRequestId:  str
    restaurantId:       str
    requestedBy:        str
    requestedByRole:    str
    requestedDate:      datetime
    overrideType:       OverrideType
    impactedOn:         ImpactedOn
    oldValue:           dict
    newValue:           dict
    reason:             OverrideReason
    justificationNotes: str
    effectiveFrom:      datetime
    effectiveTo:        Optional[datetime]  = None
    status:             OverrideStatus      = OverrideStatus.PENDING
    createdAt:          Optional[datetime]  = None
    updatedAt:          Optional[datetime]  = None

    class Config:
        populate_by_name = True
