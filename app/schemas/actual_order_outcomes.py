from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SatisfactionLevel(str, Enum):
    GOOD    = "good"
    AVERAGE = "average"
    POOR    = "poor"


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class ItemOutcomeInput(BaseModel):
    """Staff fills these per item."""
    itemCode:              str
    actualPreparedTrays:   float
    leftoverPercentage:    float = Field(..., ge=0, le=100)
    shortageOccurred:      bool  = False
    shortageAmount:        float = Field(default=0, ge=0)
    customerSatisfaction:  Optional[SatisfactionLevel] = None


class ItemOutcomeStored(ItemOutcomeInput):
    """Stored in DB — extra fields auto-computed by backend."""
    recommendedTrays:       Optional[float] = None  # from calculation_results
    manualAdjustment:       bool            = False  # auto-computed
    manualAdjustmentReason: Optional[str]   = None  # from override reason


# ── Request / Response models ─────────────────────────────────────────────────

class ActualOrderOutcomeCreate(BaseModel):
    """
    Staff fills after event is fulfilled.
    Fields auto-fetched by backend:
      requestId     — auto-fetched from calculation_results via resultId
      eventSummary  — from calculation_requests + calculation_results
      recommendedTrays per item — from calculation_results
      manualAdjustment — auto-computed
      restaurantId, outcomeId, ruleVersionId, createdAt
    """
    resultId:            str
    eventFulfilledAt:    datetime
    itemOutcomes:        List[ItemOutcomeInput] = Field(..., min_length=1)
    overallSatisfaction: Optional[SatisfactionLevel] = None
    staffNotes:          Optional[str] = None


class ActualOrderOutcomeResponse(BaseModel):
    id:                  Optional[str]             = Field(None, alias="_id")
    outcomeId:           str
    requestId:           str
    resultId:            str
    restaurantId:        str
    ruleVersionId:       Optional[str]             = None
    eventSummary:        Optional[dict]            = None
    itemOutcomes:        List[ItemOutcomeStored]
    overallSatisfaction: Optional[SatisfactionLevel] = None
    staffNotes:          Optional[str]             = None
    recordedBy:          str
    eventFulfilledAt:    datetime
    createdAt:           Optional[datetime]        = None

    class Config:
        populate_by_name = True