from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from app.schemas.learning_cycle_config import LearningCycleConfigUpdate
from app.services import learning_cycle_config_service as service

router = APIRouter(prefix="/cycle-config", tags=["Learning Cycle Config"])


@router.post("/init", response_model=dict, status_code=201)
async def initialize_config(
    minimum_order_count: int = 30,
    cycle_months: Optional[str] = Query(
        default=None,
        description="Comma separated trigger months e.g. 1,7 for Jan+Jul (default: 1,7)"
    ),
):
    """
    Initialize learning cycle config during restaurant onboarding.
    Called once at setup. Safe to call again — returns existing if already created.

    cycleMonths defines BOTH when engine fires AND cycle boundary:
      [1, 7] → fires Jan 1 and Jul 1
               H1 cycle: Jan 1 → Jun 30
               H2 cycle: Jul 1 → Dec 31

    cycleStartDate and cycleEndDate are auto-computed from cycleMonths.
    """
    parsed_months = [int(m.strip()) for m in cycle_months.split(",")] if cycle_months else None

    result = await service.initialize_config(
        minimum_order_count=minimum_order_count,
        cycle_months=parsed_months,
    )
    return {"success": True, "data": result}


@router.get("/", response_model=dict)
async def get_config():
    """
    Get current learning cycle config and cycle status.
    Shows ordersCollectedSoFar vs minimumOrderCount.
    Shows next cycle dates and bothConditionsMet flag.
    """
    result = await service.get_config()
    if not result:
        raise HTTPException(status_code=404, detail="Learning cycle config not found")
    return {"success": True, "data": result}


@router.patch("/", response_model=dict)
async def update_config(data: LearningCycleConfigUpdate):
    """
    Owner updates cycle config.
    Can change:
      minimumOrderCount — threshold for stage progression
      cycleMonths       — which months trigger the engine e.g. [1,7] or [3,9]

    cycleStartDate/cycleEndDate auto-recomputed when cycleMonths changes.
    """
    result = await service.update_config(data)
    if not result:
        raise HTTPException(status_code=404, detail="Learning cycle config not found")
    return {"success": True, "data": result}