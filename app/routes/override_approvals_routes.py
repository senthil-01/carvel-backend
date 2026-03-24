from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.constants import Decision
from app.schemas.override_approvals import OverrideApprovalCreate
from app.services import override_approvals_service as service

router = APIRouter(prefix="/override-approvals", tags=["Override Approvals"])


@router.post("/", response_model=dict, status_code=201)
async def create_override_approval(
    data: OverrideApprovalCreate,
    approved_by: str = Query(..., description="User ID from auth session"),
    approved_by_role: str = Query(..., description="Approver role from auth session")
):
    """
    Approver submits decision — approved or rejected.

    On approved + calculation override:
    → calculation_results updated with overrideApplied: true

    On approved + rule override:
    → menu_item_rules updated + new rule_version created

    On rejected:
    → audit log only — nothing changes in engine

    One approval per override_request — cannot process same request twice.
    decisionNotes mandatory for both approve and reject.
    """
    try:
        result = await service.create_override_approval(
            data=data,
            approved_by=approved_by,
            approved_by_role=approved_by_role,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def list_approvals(
    decision: Optional[Decision] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """
    List override approvals.
    Filter by decision (approved/rejected) or isActive.
    Ordered newest first.
    """
    result = await service.get_all_approvals(
        decision=decision.value if decision else None,
        is_active=is_active,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/{approval_id}", response_model=dict)
async def get_approval(approval_id: str):
    """Get a single override approval by approvalId."""
    result = await service.get_approval_by_id(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Override approval not found")
    return {"success": True, "data": result}
