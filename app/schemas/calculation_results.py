from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ResultStatus(str, Enum):
    FINAL          = "final"
    PENDING_REVIEW = "pending_review"  # ← customer placed order with flags — staff resolving
    OVERRIDDEN     = "overridden"      # ← staff resolved all flags
    VOIDED         = "voided"          # ← customer cancelled


# ── Summary ───────────────────────────────────────────────────────────────────

class ResultSummary(BaseModel):
    effectiveGuests:   float
    kidsFactor:        float
    eventType:         str
    serviceStyle:      str
    eventMultiplier:   float
    serviceMultiplier: float
    bufferApplied:     float


# ── Trace objects ─────────────────────────────────────────────────────────────

class Path1Trace(BaseModel):
    step1_effectiveGuests: float
    step2_adjustedDemand:  float
    step3_finalDemand:     float
    step4_scenarioUsed:    str
    step4_spread:          dict   # { S, M, L }
    step5_result:          dict   # { L, M, S counts }


class Path2Trace(BaseModel):
    step1_effectiveGuests: float
    step2_scenarioUsed:    str
    step2_piecesPerPerson: float
    step3_totalPieces:     float


# ── Item result ───────────────────────────────────────────────────────────────

class ItemResult(BaseModel):
    itemCode:     str
    menuName:     str
    category:     str
    vegNonVeg:    str
    sellByCount:  bool
    customMode:   bool = False
    scenarioUsed: Optional[str] = None
    message:      Optional[str] = None   # custom mode message to sales/ops

    # Path 1 only
    trayResult:   Optional[dict] = None  # { L, M, S }
    trace:        Optional[dict] = None  # Path1Trace or Path2Trace

    # Path 2 only
    totalPieces:  Optional[float] = None


# ── Request / Response ────────────────────────────────────────────────────────

class CalculationResultCreate(BaseModel):
    """
    Internal only — called by engine service directly, no HTTP route.
    """
    requestId:    str
    ruleVersionId: str
    summary:      ResultSummary
    itemResults:  List[ItemResult]


class CalculationResultResponse(BaseModel):
    id:               Optional[str]      = Field(None, alias="_id")
    resultId:         str
    requestId:        str
    restaurantId:     str
    ruleVersionId:    str
    summary:          ResultSummary
    itemResults:      List[ItemResult]
    totalAmount:      float              = 0.0  # sum of calculable items — updates on resolution
    hasCustomMode:    bool               = False
    hasRemainderFlag: bool               = False
    overrideApplied:  bool               = False
    overrideId:       Optional[str]      = None
    status:           str
    calculatedAt:     Optional[datetime] = None
    createdAt:        Optional[datetime] = None

    class Config:
        populate_by_name = True