from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class LearningStage(str, Enum):
    STAGE_1 = "stage_1"
    STAGE_2 = "stage_2"
    STAGE_3 = "stage_3"


class RecommendationStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class CurrentRule(BaseModel):
    ruleField:     str
    currentValue:  Optional[float] = None
    currentSpread: Optional[dict]  = None  # { S, M, L }


class SuggestedRule(BaseModel):
    ruleField:       str
    suggestedValue:  Optional[float] = None
    suggestedSpread: Optional[dict]  = None  # { S, M, L }


class Analytics(BaseModel):
    avgLeftoverPct:                  float
    shortageFrequencyPct:            float
    avgActualVsRecommendedVariance:  float
    estimatedImpact:                 str


# ── Request / Response models ─────────────────────────────────────────────────

class RuleRecommendationCreate(BaseModel):
    """
    Internal only — called by learning engine background job.
    Never manually created.
    """
    ruleVersionId:  str
    cycleId:        str
    cycleStartDate: datetime
    cycleEndDate:   datetime
    ordersAnalysed: int
    itemCode:       str
    menuName:       str
    segment:        str
    learningStage:  LearningStage
    currentRule:    CurrentRule
    suggestedRule:  SuggestedRule
    confidence:     float = Field(..., ge=0, le=1)
    basedOnOrders:  int
    reason:         str
    analytics:      Analytics


class RuleRecommendationResponse(BaseModel):
    id:                   Optional[str]               = Field(None, alias="_id")
    recommendationId:     str
    restaurantId:         str
    ruleVersionId:        str
    cycleId:              str
    cycleStartDate:       datetime
    cycleEndDate:         datetime
    triggerType:          str
    ordersAnalysed:       int
    itemCode:             str
    menuName:             str
    segment:              str
    learningStage:        LearningStage
    currentRule:          CurrentRule
    suggestedRule:        SuggestedRule
    confidence:           float
    basedOnOrders:        int
    reason:               str
    analytics:            Analytics
    status:               RecommendationStatus = RecommendationStatus.PENDING
    approvedBy:           Optional[str]        = None
    approvedAt:           Optional[datetime]   = None
    newRuleVersionCreated: Optional[str]       = None
    generatedAt:          Optional[datetime]   = None
    createdAt:            Optional[datetime]   = None

    class Config:
        populate_by_name = True
