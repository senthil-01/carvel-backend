from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.constants import RESTAURANT_ID
from app.schemas.rule_multipliers import RuleMultiplierCreate, RuleMultiplierUpdate
from app.services import rule_multipliers_service as service

router = APIRouter(prefix="/multipliers", tags=["Rule Multipliers"])


@router.post("/", response_model=dict, status_code=201)
async def create_multiplier(data: RuleMultiplierCreate):
    """Create a single multiplier. Called during admin setup."""
    result = await service.create_multiplier(data)
    return {"success": True, "data": result}


@router.delete("/", response_model=dict)
async def delete_multiplier(
    rule_version_id: str = Query(...),
    multiplier_type: str = Query(...),
    key: Optional[str] = Query(None)
):
    result = await service.delete_multiplier(rule_version_id, multiplier_type, key)
    if not result:
        raise HTTPException(status_code=404, detail="Multiplier not found")
    return {"success": True, "message": "Deleted successfully", "deleted_count": result}


@router.post("/seed", response_model=dict, status_code=201)
async def seed_multipliers(version_id: str = Query(...)):
    """
    Seed default multipliers during restaurant onboarding.
    Called once during initial setup.
    """
    await service.seed_default_multipliers(version_id)
    return {"success": True, "message": "Default multipliers seeded"}


@router.get("/", response_model=dict)
async def list_multipliers(
    multiplier_type: str = Query(...),
    is_active: Optional[bool] = Query(None)
):
    """
    List multipliers. Filter by type (event/service/audience/buffer/seasonal).
    Used by admin UI to show multiplier setup screen.
    """
    items = await service.get_multipliers_by_type(multiplier_type, is_active)
    return {"success": True, "count": len(items), "data": items}


@router.patch("/{key}", response_model=dict)
async def update_multiplier(
    key: str,
    multiplier_type: str = Query(...),
    data: RuleMultiplierUpdate = ...
):
    """
    Update a multiplier value.
    Goes through override/approval workflow for rule changes.
    """
    result = await service.update_multiplier(key, multiplier_type, data)
    if not result:
        raise HTTPException(status_code=404, detail="Multiplier not found")
    return {"success": True, "data": result}
