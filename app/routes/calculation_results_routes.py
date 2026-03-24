from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.schemas.calculation_results import ResultStatus
from app.services import calculation_results_service as service
from pydantic import BaseModel

router = APIRouter(prefix="/calculation-results", tags=["Calculation Results"])


class ResultStatusUpdate(BaseModel):
    status: str


class ManualEntryPayload(BaseModel):
    requestId:        str
    itemCode:         str
    trayResult:       Optional[dict]  = None   # Path 1 — { L, M, S }
    totalPieces:      Optional[float] = None   # Path 2 — piece count


class AcknowledgePayload(BaseModel):
    requestId:         str
    itemCode:          str
    acknowledgedBy:    str
    extraAmountAdded:  Optional[float] = None  # sales/ops adds if remainder needs extra
    extraAmountNote:   Optional[str]   = None


@router.get("/", response_model=dict)
async def list_results(
    status: Optional[ResultStatus] = Query(None),
    event_type: Optional[str] = Query(None),
    has_custom_mode: Optional[bool] = Query(None),
    has_remainder_flag: Optional[bool] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """List all calculation results. Ordered newest first."""
    result = await service.get_all_results(
        status=status.value if status else None,
        event_type=event_type,
        has_custom_mode=has_custom_mode,
        has_remainder_flag=has_remainder_flag,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/request/{request_id}", response_model=dict)
async def get_result_by_request(request_id: str):
    """Get fully resolved calculation result by requestId."""
    result = await service.get_result_by_request_id(request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found for this request")
    return {"success": True, "data": result}


@router.get("/{result_id}", response_model=dict)
async def get_result(result_id: str):
    """Get a single calculation result by resultId."""
    result = await service.get_result_by_id(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Calculation result not found")
    return {"success": True, "data": result}


@router.patch("/manual-entry", response_model=dict)
async def manual_entry(
    data: ManualEntryPayload,
    requested_by: str = Query(..., description="User ID from auth session"),
    requested_by_role: str = Query(..., description="Role from auth session"),
):
    """
    Sales/ops manually enters tray count or piece count for custom mode items.
    Auto-creates override_request in C6 for audit and approval.
    When all custom mode and remainder flags resolved → saves to calculation_results.
    """
    if not data.trayResult and data.totalPieces is None:
        raise HTTPException(
            status_code=400,
            detail="Either trayResult or totalPieces must be provided"
        )

    result = await service.update_manual_entry(
        request_id=data.requestId,
        item_code=data.itemCode,
        requested_by=requested_by,
        requested_by_role=requested_by_role,
        tray_result=data.trayResult,
        total_pieces=data.totalPieces,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Request not found or item is not in custom mode"
        )
    return {"success": True, "data": result}


@router.patch("/by-request/{request_id}/status", response_model=dict)
async def update_result_status(request_id: str, data: ResultStatusUpdate):
    """
    Update calculation_results status using requestId.
    Called by CheckoutPage when customer confirms order:
      final → order_placed
    Learning engine reads calculation_results with status=order_placed.
    """
    allowed = {"pending_review", "overridden", "voided"}
    if data.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {allowed}")

    result = await service.update_result_status_by_request_id(request_id, data.status)
    if not result:
        raise HTTPException(status_code=404, detail="Calculation result not found for this request")
    return {"success": True, "data": result}


@router.patch("/acknowledge-remainder", response_model=dict)
async def acknowledge_remainder(data: AcknowledgePayload):
    """
    Sales/ops acknowledges remainderFlag for a specific item.
    After reviewing message they inform chef operationally.
    When all flags acknowledged and no custom mode → saves to calculation_results.
    """
    result = await service.acknowledge_remainder(
        request_id=data.requestId,
        item_code=data.itemCode,
        acknowledged_by=data.acknowledgedBy,
        extra_amount_added=data.extraAmountAdded,
        extra_amount_note=data.extraAmountNote,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Request not found or no remainder flag for this item"
        )
    return {"success": True, "data": result}