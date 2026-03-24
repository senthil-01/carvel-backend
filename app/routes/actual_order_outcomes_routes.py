from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.schemas.actual_order_outcomes import ActualOrderOutcomeCreate
from app.services import actual_order_outcomes_service as service

router = APIRouter(prefix="/outcomes", tags=["Actual Order Outcomes"])


@router.post("/", response_model=dict, status_code=201)
async def create_outcome(
    data: ActualOrderOutcomeCreate,
    recorded_by: str = Query(..., description="User ID from auth session")
):
    """
    Record actual outcome after event is fulfilled.
    Staff provides resultId — requestId auto-fetched from result.
    eventSummary and recommendedTrays auto-fetched from linked collections.
    manualAdjustment auto-computed.
    Records are immutable once created — no edit, no delete.
    Increments ordersCollectedSoFar in learning_cycle_config.
    """
    try:
        result = await service.create_outcome(data, recorded_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def list_outcomes(
    event_type: Optional[str] = Query(None),
    service_style: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """
    List all outcomes.
    Filter by event_type, service_style, or item_code.
    Ordered newest first.
    """
    result = await service.get_all_outcomes(
        event_type=event_type,
        service_style=service_style,
        item_code=item_code,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/result/{result_id}", response_model=dict)
async def get_outcome_by_result(result_id: str):
    """Get outcome by resultId — primary link for staff workflow."""
    result = await service.get_outcome_by_result_id(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Outcome not found for this result")
    return {"success": True, "data": result}


@router.get("/{outcome_id}", response_model=dict)
async def get_outcome(outcome_id: str):
    """Get a single outcome by outcomeId."""
    result = await service.get_outcome_by_id(outcome_id)
    if not result:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return {"success": True, "data": result}