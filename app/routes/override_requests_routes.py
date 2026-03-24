from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.constants import OverrideStatus
from app.schemas.override_requests import OverrideRequestCreate
from app.services import override_requests_service as service

router = APIRouter(prefix="/override-requests", tags=["Override Requests"])


@router.post("/", response_model=dict, status_code=201)
async def create_override_request(
    data: OverrideRequestCreate,
    requested_by: str = Query(..., description="User ID from auth session"),
    requested_by_role: str = Query(..., description="Role from auth session")
):
    """
    Raise a new override request.
    Raised by sales_rep / catering_manager / operations_manager.
    Always stored with status: pending.
    Collection 7 handles approval/rejection.
    """
    result = await service.create_override_request(
        data=data,
        requested_by=requested_by,
        requested_by_role=requested_by_role,
    )
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def list_override_requests(
    status: Optional[OverrideStatus] = Query(None),
    override_type: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """
    List override requests.
    Filter by status, override_type, or item_code.
    Ordered newest first.
    """
    result = await service.get_all_override_requests(
        status=status.value if status else None,
        override_type=override_type,
        item_code=item_code,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/{override_request_id}", response_model=dict)
async def get_override_request(override_request_id: str):
    """Get a single override request by overrideRequestId."""
    result = await service.get_override_request_by_id(override_request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Override request not found")
    return {"success": True, "data": result}
