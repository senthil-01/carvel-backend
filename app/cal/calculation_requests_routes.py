from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
from app.core.constants import RESTAURANT_ID
from app.schemas.calculation_requests import (
    CalculationRequestCreate,
    CalculationRequestStatusUpdate,
    RequestStatus,
)
from app.services import calculation_requests_service as service

router = APIRouter(prefix="/calculation-requests", tags=["Calculation Requests"])


@router.post("/", response_model=dict, status_code=201)
async def create_calculation_request(
    data: CalculationRequestCreate,
    requested_by: str = Query(..., description="User ID from auth session")
):
    """
    Submit a new catering calculation request from any channel.
    ruleVersionId is auto-stamped with the active rule version.
    """
    try:
        result = await service.create_calculation_request(data, requested_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def list_calculation_requests(
    status:         Optional[RequestStatus] = Query(None),
    event_type:     Optional[str]           = Query(None),
    from_date:      Optional[datetime]      = Query(None),
    to_date:        Optional[datetime]      = Query(None),
    exclude_voided: bool                    = Query(default=False),
    page:           int                     = Query(default=1,  ge=1),
    page_size:      int                     = Query(default=20, ge=1, le=100)
):
    """
    List calculation requests for a restaurant.
    Ordered newest first. Supports status, event_type, and date range filters.
    exclude_voided=true hides voided orders from staff dashboard.
    """
    result = await service.get_all_requests(
        status=status.value if status else None,
        event_type=event_type,
        from_date=from_date,
        to_date=to_date,
        exclude_voided=exclude_voided,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/pending/queue", response_model=dict)
async def get_pending_queue():
    """
    Fetch all pending requests in FIFO order.
    Internal — used by the calculation engine worker.
    """
    results = await service.get_pending_queue()
    return {"success": True, "count": len(results), "data": results}


@router.patch("/{request_id}/void", response_model=dict)
async def void_request(request_id: str):
    """
    Void a request — customer left checkout without placing order.
    """
    result = await service.void_request(request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"success": True, "data": result}


@router.get("/{request_id}", response_model=dict)
async def get_calculation_request(request_id: str):
    """Get complete user order details using requestId. Fetch a single calculation request by requestId."""
    result = await service.get_request_by_id(request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Calculation request not found")
    return {"success": True, "data": result}