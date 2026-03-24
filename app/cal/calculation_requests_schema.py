from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class RequestChannel(str, Enum):
    WEB_APP       = "web_app"
    ADMIN_CONSOLE = "admin_console"
    SALES_CONSOLE = "sales_console"
    VOICE_AGENT   = "voice_agent"
    CHAT_FORM     = "chat_form"


# EventType and ServiceStyle are plain str — fetched dynamically from rule_multipliers DB
# No hardcoding — admin controls valid values via DB

class RequestStatus(str, Enum):
    PENDING        = "pending"
    PROCESSING     = "processing"
    PENDING_REVIEW = "pending_review"   # ← has customMode or remainderFlag
    COMPLETED      = "completed"        # ← engine done / staff resolved
    VOIDED         = "voided"           # ← customer left checkout
    FAILED         = "failed"


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class EventDetails(BaseModel):
    eventName:    str           = Field(..., min_length=1)
    eventType:    str           = Field(..., min_length=1)  # dynamic — from rule_multipliers
    eventDate:    datetime
    serviceStyle: str           = Field(..., min_length=1)  # dynamic — from rule_multipliers
    venue:        Optional[str] = None

    @model_validator(mode="after")
    def validate_event_date(self):
        from datetime import timezone
        now        = datetime.now(timezone.utc)
        event_date = self.eventDate
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        if event_date < now:
            raise ValueError("Event date must be today or in the future")
        return self


class GuestDetailsInput(BaseModel):
    """User-facing input — only adultCount and kidsCount. totalGuests never asked."""
    adultCount: int = Field(..., ge=0)
    kidsCount:  int = Field(default=0, ge=0)


class GuestDetailsStored(GuestDetailsInput):
    """Stored in DB — totalGuests auto-computed before insert."""
    totalGuests: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def compute_total(self):
        self.totalGuests = self.adultCount + self.kidsCount
        return self


class MenuItem(BaseModel):
    itemCode:  str
    category:  str
    vegNonVeg: str = Field(..., pattern="^(Veg|Non Veg)$")


class SpecialFlags(BaseModel):
    vipEvent:     bool          = False
    outdoorEvent: bool          = False
    customNote:   Optional[str] = None


# ── Request / Response models ─────────────────────────────────────────────────

class CalculationRequestCreate(BaseModel):
    """
    Payload accepted from any channel.
    Fields injected by backend:
      requestId, ruleVersionId, requestedBy, status, normalizedAt, createdAt, bufferPercent
    """
    requestChannel: RequestChannel
    eventDetails:   EventDetails
    guestDetails:   GuestDetailsInput
    menuItems:      List[MenuItem] = Field(..., min_length=1)
    bufferPercent:  Optional[float] = Field(default=None, ge=0, le=100)
    specialFlags:   SpecialFlags = Field(default_factory=SpecialFlags)


class CalculationRequestResponse(BaseModel):
    id:               Optional[str]      = Field(None, alias="_id")
    requestId:        str
    restaurantId:     str
    requestChannel:   RequestChannel
    eventDetails:     EventDetails
    guestDetails:     GuestDetailsStored
    menuItems:        List[MenuItem]
    bufferPercent:    Optional[float]
    specialFlags:     SpecialFlags
    ruleVersionId:    str
    requestedBy:      str
    status:           RequestStatus      = RequestStatus.PENDING
    hasCustomMode:    Optional[bool]     = None
    hasRemainderFlag: Optional[bool]     = None
    normalizedAt:     Optional[datetime] = None
    createdAt:        Optional[datetime] = None

    class Config:
        populate_by_name = True


class CalculationRequestStatusUpdate(BaseModel):
    """Internal — used by the engine to advance status only."""
    status:       RequestStatus
    normalizedAt: Optional[datetime] = None