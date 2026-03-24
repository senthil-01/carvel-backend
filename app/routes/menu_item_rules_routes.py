from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.constants import RESTAURANT_ID
from app.schemas.menu_item_rules import MenuItemRuleCreate, MenuItemPriceUpdate
from app.services import menu_item_rules_service as service

router = APIRouter(prefix="/menu-items", tags=["Menu Item Rules"])


@router.post("/", response_model=dict, status_code=201)
async def create_menu_item(data: MenuItemRuleCreate):
    """Create a menu item rule. Called by import service — not directly by user."""
    result = await service.create_menu_item_rule(data)
    return {"success": True, "data": result}


@router.delete("/{item_code}", response_model=dict, summary="delete menu item")
async def delete_menu_item_rule(
    item_code: str,
    rule_version_id: str = Query(...)
):
    """delete menu item."""
    result = await service.delete_menu_item_rule(rule_version_id, item_code)
    if not result:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"success": True, "message": f"Menu item '{item_code}' deleted successfully"}


@router.get("/", response_model=dict)
async def list_menu_items(
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sell_by_count: Optional[bool] = Query(None),
    veg_non_veg: Optional[str] = Query(None),
    style: Optional[str] = Query(None)
):
    """List all menu items. Filter by category, isActive, sellByCount, veg_non_veg."""
    items = await service.get_all_menu_items(category, is_active, sell_by_count, veg_non_veg, style)
    return {"success": True, "count": len(items), "data": items}



@router.get("/version/{version_id}", response_model=dict)
async def get_items_by_version(version_id: str):
    """Get all items belonging to a specific rule version. Used for audit."""
    items = await service.get_menu_items_by_version(version_id)
    return {"success": True, "count": len(items), "data": items}


@router.get("/{item_code}/scenario/{scenario_name}", response_model=dict)
async def get_item_scenario(item_code: str, scenario_name: str):
    """
    Get a specific scenario spread for an item.
    Returns customMode=true if scenario not defined.
    Used by calculation engine to get S/M/L spread values.
    """
    result = await service.get_item_scenario(item_code, scenario_name)
    if result is None:
        return {
            "success": False,
            "customMode": True,
            "message": f"Scenario '{scenario_name}' not defined for {item_code}. Custom mode required."
        }
    return {"success": True, "data": result}


@router.get("/{item_code}/count-scenario/{scenario_name}", response_model=dict)
async def get_item_count_scenario(item_code: str, scenario_name: str):
    """
    Get count scenario for sell-by-count items (Bread, Count Appetizer, Dessert).
    Returns piecesPerPerson for the given scenario.
    """
    result = await service.get_item_count_scenario(item_code, scenario_name)
    if result is None:
        return {
            "success": False,
            "customMode": True,
            "message": f"Count scenario '{scenario_name}' not defined for {item_code}."
        }
    return {"success": True, "data": result}


@router.get("/{item_code}", response_model=dict)
async def get_menu_item(item_code: str):
    """Get single menu item by itemCode. Returns active rule only."""
    item = await service.get_menu_item_by_code(item_code)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Menu item {item_code} not found or inactive"
        )
    return {"success": True, "data": item}


@router.post("/seed-prices", response_model=dict)
async def seed_menu_item_prices(rule_version_id: str = Query(...)):
    """Seed initial prices for all menu items."""
    result = await service.seed_prices(rule_version_id)
    return {"success": True, "data": result}


@router.patch("/{item_code}/price", response_model=dict)
async def update_menu_item_price(
    item_code: str,
    rule_version_id: str = Query(...),
    data: MenuItemPriceUpdate = ...
):
    """Update price for a menu item based on sellByCount from DB."""
    result = await service.update_menu_item_price(rule_version_id, item_code, data)
    if not result:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"success": True, "data": result}
