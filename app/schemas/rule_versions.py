from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.core.constants import VersionStatus, VersionSource


class RuleVersionCreate(BaseModel):
    # restaurantId → sourced from RESTAURANT_ID constant
    versionLabel: str
    source: VersionSource
    importJobId: Optional[str] = None
    totalItemsImported: int = 0
    notes: Optional[str] = None
    publishedBy: str  # from auth session


class RuleVersionResponse(RuleVersionCreate):
    id: Optional[str] = Field(None, alias="_id")
    versionId: Optional[str] = None
    versionNumber: Optional[int] = None
    status: Optional[VersionStatus] = None
    previousVersionId: Optional[str] = None
    activatedAt: Optional[datetime] = None
    deactivatedAt: Optional[datetime] = None
    publishedAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
