from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime
from app.core.constants import MultiplierType


class RuleMultiplierCreate(BaseModel):
    ruleVersionId: str
    multiplierType: MultiplierType
    key: Optional[str] = None         # auto-generated from label
    label: str
    multiplier: Optional[float] = None  # not used for buffer type
    bufferPercent: Optional[float] = None  # buffer type only
    isActive: bool = True
    # restaurantId → sourced from RESTAURANT_ID constant

    @model_validator(mode="after")
    def validate_fields(self):
            # auto-generate key from label
            if not self.key and self.label:
                self.key = self.label.lower().strip().replace(" ", "_")

            if self.multiplierType == MultiplierType.BUFFER:
                if self.bufferPercent is None:
                    raise ValueError("bufferPercent is required for buffer type")
                self.multiplier = None  # strip multiplier for buffer type

            else:
                if self.multiplier is None:
                    raise ValueError("multiplier value is required for event and service types")
                if self.multiplier <= 0:
                    raise ValueError("multiplier must be a positive number")
                self.bufferPercent = None  # strip bufferPercent for non-buffer types

            return self

class RuleMultiplierResponse(RuleMultiplierCreate):
    id: Optional[str] = Field(None, alias="_id")
    createdAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class RuleMultiplierUpdate(BaseModel):
    label: Optional[str] = None
    multiplier: Optional[float] = None
    bufferPercent: Optional[float] = None
    isActive: Optional[bool] = None
