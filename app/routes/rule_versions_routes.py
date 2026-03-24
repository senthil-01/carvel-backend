from fastapi import APIRouter, HTTPException, Query
from app.core.constants import RESTAURANT_ID
from app.schemas.rule_versions import RuleVersionCreate
from app.services import rule_versions_service as service

router = APIRouter(prefix="/versions", tags=["Rule Versions"])


@router.post("/", response_model=dict, status_code=201)
async def create_version(data: RuleVersionCreate):
    """
    Create a new rule version in DRAFT status.
    Called automatically by import service or approval workflow.
    """
    result = await service.create_version(data)
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def list_versions():
    """
    List all versions for a restaurant ordered newest first.
    Used for version history screen in admin UI.
    """
    versions = await service.get_all_versions()
    return {"success": True, "count": len(versions), "data": versions}


@router.get("/active", response_model=dict)
async def get_active_version():
    """
    Get the currently active rule version.
    Called by calculation engine on every request.
    """
    version = await service.get_active_version()
    if not version:
        raise HTTPException(
            status_code=404,
            detail="No active rule version found. Please import rules first."
        )
    return {"success": True, "data": version}


@router.post("/{version_id}/activate", response_model=dict)
async def activate_version(version_id: str):
    """
    Activate a draft version. Archives current active version.
    Admin only.
    """
    result = await service.activate_version(version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"success": True, "message": "Version activated", "data": result}


@router.post("/{version_id}/rollback", response_model=dict)
async def rollback_version(version_id: str):
    """
    Rollback to a previous version. Admin only.
    Archives current active version and re-activates the target version.
    """
    result = await service.rollback_version(version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"success": True, "message": "Rolled back successfully", "data": result}


@router.get("/{version_id}", response_model=dict)
async def get_version(version_id: str):
    """Get a specific version by ID."""
    version = await service.get_version_by_id(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"success": True, "data": version}
