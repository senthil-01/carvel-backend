from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class CycleSchedule(BaseModel):
    cycleMonths: List[int] = Field(default=[1, 7])  # January and July
    cycleDates:  List[datetime] = []                 # pre-computed trigger dates


class CurrentCycle(BaseModel):
    cycleId:                  str
    cycleStartDate:           datetime
    cycleEndDate:             datetime
    status:                   str  = "active"   # active / completed
    ordersCollectedSoFar:     int  = 0
    minimumMet:               bool = False
    dateMet:                  bool = False
    bothConditionsMet:        bool = False
    recommendationsGenerated: bool = False


class CycleHistory(BaseModel):
    cycleId:              str
    ordersAnalysed:       int
    recommendationsCount: int
    triggeredAt:          datetime


# ── Request / Response models ─────────────────────────────────────────────────

class LearningCycleConfigUpdate(BaseModel):
    """Owner can update these fields only."""
    minimumOrderCount: Optional[int]       = None
    cycleMonths:       Optional[List[int]] = None  # e.g. [1, 7] or [3, 9]


class LearningCycleConfigResponse(BaseModel):
    id:                Optional[str]      = Field(None, alias="_id")
    configId:          str
    restaurantId:      str
    cycleSchedule:     CycleSchedule
    minimumOrderCount: int
    currentCycle:      CurrentCycle
    cycleHistory:      List[CycleHistory] = []
    isActive:          bool               = True
    createdAt:         Optional[datetime] = None
    updatedAt:         Optional[datetime] = None

    class Config:
        populate_by_name = True