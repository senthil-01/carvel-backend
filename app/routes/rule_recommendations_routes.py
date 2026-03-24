from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.schemas.rule_recommendations import RecommendationStatus
from app.services import rule_recommendations_service as service

router = APIRouter(prefix="/recommendations", tags=["Rule Recommendations"])


@router.get("/", response_model=dict)
async def list_recommendations(
    status: Optional[RecommendationStatus] = Query(None),
    cycle_id: Optional[str] = Query(None),
    item_code: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """
    List rule recommendations.
    Filter by status, cycleId, or itemCode.
    Ordered newest first.
    Owner sees pending recommendations grouped by cycleId on dashboard.
    """
    result = await service.get_all_recommendations(
        status=status.value if status else None,
        cycle_id=cycle_id,
        item_code=item_code,
        page=page,
        page_size=page_size
    )
    return {"success": True, **result}


@router.get("/{recommendation_id}", response_model=dict)
async def get_recommendation(recommendation_id: str):
    """Get a single recommendation by recommendationId."""
    result = await service.get_recommendation_by_id(recommendation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return {"success": True, "data": result}


@router.patch("/{recommendation_id}/approve", response_model=dict)
async def approve_recommendation(
    recommendation_id: str,
    approved_by: str = Query(..., description="Owner user ID from auth session")
):
    """
    Owner approves a recommendation.
    → new rule_version created
    → menu_item_rules updated with suggested spread
    → newRuleVersionCreated populated
    Owner role only.
    """
    result = await service.approve_recommendation(recommendation_id, approved_by)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found or already processed"
        )
    return {"success": True, "data": result}


@router.patch("/{recommendation_id}/reject", response_model=dict)
async def reject_recommendation(
    recommendation_id: str,
    rejected_by: str = Query(..., description="Owner user ID from auth session")
):
    """
    Owner rejects a recommendation.
    → audit log only — nothing changes in engine
    → never resurfaces
    Owner role only.
    """
    result = await service.reject_recommendation(recommendation_id, rejected_by)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found or already processed"
        )
    return {"success": True, "data": result}
