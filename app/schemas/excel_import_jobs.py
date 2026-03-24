from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.core.constants import ImportStatus


class ValidationError(BaseModel):
    sheet: str
    row: int
    itemName: Optional[str] = None
    field: str
    issue: str


class ValidationResult(BaseModel):
    passed: bool
    totalRowsFound: int = 0
    totalRowsValid: int = 0
    totalRowsSkipped: int = 0
    errors: List[ValidationError] = []


class ImportResult(BaseModel):
    totalItemsImported: int = 0
    totalMultipliersImported: int = 0
    categoriesImported: List[str] = []
    ruleVersionCreated: Optional[str] = None


class ExcelImportJobCreate(BaseModel):
    uploadedBy: str
    fileName: str
    fileSize: int
    filePath: str
    # restaurantId → sourced from RESTAURANT_ID constant


class ExcelImportJobResponse(ExcelImportJobCreate):
    id: Optional[str] = Field(None, alias="_id")
    importJobId: Optional[str] = None
    sheets: Optional[List[str]] = []
    status: Optional[ImportStatus] = None
    validationResult: Optional[ValidationResult] = None
    importResult: Optional[ImportResult] = None
    completedAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
