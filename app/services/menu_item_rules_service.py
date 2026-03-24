from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from app.core.database import get_db
from app.core.constants import RESTAURANT_ID
from app.schemas.menu_item_rules import MenuItemRuleCreate, MenuItemRuleUpdate, MenuItemPriceUpdate

COLLECTION = "menu_item_rules"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def create_menu_item_rule(data: MenuItemRuleCreate) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = data.model_dump(exclude_none=True)

    # Auto-generate itemCode from menuName
    doc["itemCode"] = doc["menuName"].upper().replace(" ", "_").replace("-", "_")

    # Normalize vegNonVeg
    if doc["vegNonVeg"] and "non" in doc["vegNonVeg"].lower():
        doc["vegNonVeg"] = "Non Veg"

    # Normalize category
    doc["category"] = doc["category"].replace("Entrée", "Entree").replace("entrée", "entree")

    # Strip string fields
    doc["menuName"] = doc["menuName"].strip()
    doc["style"] = doc["style"].strip() if doc.get("style") else None
    doc["group"] = doc["group"].strip() if doc.get("group") else None

    doc["restaurantId"] = RESTAURANT_ID
    doc["createdAt"] = now
    doc["updatedAt"] = now

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def delete_menu_item_rule(rule_version_id: str, item_code: str) -> bool:
    db = get_db()
    result = await db[COLLECTION].find_one_and_delete({
        "restaurantId": RESTAURANT_ID,
        "ruleVersionId": rule_version_id,
        "itemCode": item_code
    })
    return result is not None


async def get_all_menu_items(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    sell_by_count: Optional[bool] = None,
    veg_non_veg: Optional[str] = None,
    style: Optional[str] = None
) -> list:
    db = get_db()
    query = {"restaurantId": RESTAURANT_ID}
    if category:
        query["category"] = category
    if is_active is not None:
        query["isActive"] = is_active
    if sell_by_count is not None:
        query["sellByCount"] = sell_by_count
    if veg_non_veg:
        query["vegNonVeg"] = veg_non_veg
    if style:
        query["style"] = style
    cursor = db[COLLECTION].find(query)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def get_menu_item_by_code(item_code: str) -> Optional[dict]:
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode": item_code,
        "isActive": True
    })
    return _serialize(doc) if doc else None


async def get_menu_items_by_version(version_id: str) -> list:
    db = get_db()
    cursor = db[COLLECTION].find({
        "restaurantId": RESTAURANT_ID,
        "ruleVersionId": version_id
    })
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def deactivate_items_by_version(version_id: str):
    db = get_db()
    await db[COLLECTION].update_many(
        {"restaurantId": RESTAURANT_ID, "ruleVersionId": {"$ne": version_id}},
        {"$set": {"isActive": False}}
    )


async def get_item_count_scenario(item_code: str, scenario_name: str) -> Optional[dict]:
    """
    Get count scenario for sell-by-count items (Bread, Count Appetizer, Dessert).
    Returns piecesPerPerson for the given scenario.
    Returns None if not defined → custom mode.
    """
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode": item_code,
        "isActive": True
    })
    if not doc:
        return None

    count_scenarios = doc.get("countScenarios", {})
    if not count_scenarios or scenario_name not in count_scenarios:
        return None

    return {
        "itemCode": item_code,
        "menuName": doc.get("menuName"),
        "category": doc.get("category"),
        "sellByCount": True,
        "size": doc.get("size"),
        "scenario": scenario_name,
        "piecesPerPerson": count_scenarios[scenario_name].get("piecesPerPerson"),
        "roundingRule": doc.get("roundingRule", "full_tray"),
    }


async def get_item_scenario(item_code: str, scenario_name: str) -> Optional[dict]:
    """
    Get specific scenario spread for one item.
    Returns None if scenario not defined → triggers custom mode.
    """
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode": item_code,
        "isActive": True
    })
    if not doc:
        return None
    scenarios = doc.get("scenarios", {})
    if not scenarios or scenario_name not in scenarios:
        return None
    return {
        "itemCode": item_code,
        "menuName": doc.get("menuName"),
        "category": doc.get("category"),
        "vegNonVeg": doc.get("vegNonVeg"),
        "sellByCount": doc.get("sellByCount"),
        "scenario": scenario_name,
        "servesPerTray": scenarios[scenario_name].get("servesPerTray"),
        "spread": scenarios[scenario_name].get("spread"),
        "roundingRule": doc.get("roundingRule", "full_tray"),
        "adjustmentMultiplier": doc.get("adjustmentMultiplier", 1.0),
        "property": doc.get("property"),
        "riceType": doc.get("riceType"),
    }


async def get_items_by_codes(item_codes: list) -> list:
    """
    Get multiple items by item codes in one DB query.
    Used by calculation engine to fetch all ordered items at once.
    """
    db = get_db()
    cursor = db[COLLECTION].find({
        "restaurantId": RESTAURANT_ID,
        "itemCode": {"$in": item_codes},
        "isActive": True
    })
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def get_combo_spread_rules() -> Optional[dict]:
    """
    Get combo spread rules stored as COMBO_SPREAD_APPETIZER document.
    Used by calculation engine when order has mixed veg+nonveg appetizers.
    """
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode": "COMBO_SPREAD_APPETIZER",
        "isActive": True
    })
    return _serialize(doc) if doc else None


async def update_menu_item_rule(item_code: str, data: MenuItemRuleUpdate, new_version_id: str) -> Optional[dict]:
    """Update only through approved override workflow"""
    db = get_db()
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updatedAt"] = datetime.now(timezone.utc)
    update_data["ruleVersionId"] = new_version_id
    result = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "itemCode": item_code, "isActive": True},
        {"$set": update_data},
        return_document=True
    )
    return _serialize(result) if result else None


async def update_menu_item_price(rule_version_id: str, item_code: str, data: MenuItemPriceUpdate) -> Optional[dict]:
    db = get_db()

    existing = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode": item_code
    })
    if not existing:
        return None

    sell_by_count = existing.get("sellByCount")
    update_data = {}

    if sell_by_count:
        if data.price is None:
            raise HTTPException(status_code=400, detail="price is required for sellByCount items")
        update_data["price"] = data.price
    else:
        if data.trayPrice is None:
            raise HTTPException(status_code=400, detail="trayPrice is required for tray items")
        update_data["trayPrice"] = data.trayPrice.model_dump(exclude_none=True)

    update_data["updatedAt"] = datetime.now(timezone.utc)

    result = await db[COLLECTION].find_one_and_update(
        {
            "restaurantId": RESTAURANT_ID,
            "ruleVersionId": rule_version_id,
            "itemCode": item_code
        },
        {"$set": update_data},
        return_document=True
    )
    return _serialize(result) if result else None


# Tray prices — sellByCount = false
TRAY_PRICES = {
    ("Appetizer", "Veg"):     {"S": 800,  "M": 1500, "L": 2200},
    ("Appetizer", "Non Veg"): {"S": 1000, "M": 1800, "L": 2600},
    ("Entree", "Veg"):        {"S": 1100, "M": 1900, "L": 2700},
    ("Entree", "Non Veg"):    {"S": 1300, "M": 2200, "L": 3000},
    ("Rice", "Veg"):          {"S": 900,  "M": 1600, "L": 2400},
    ("Rice", "Non Veg"):      {"S": 1100, "M": 2000, "L": 2800},
}

# Piece prices — sellByCount = true (Bread, Appetizer pieces, Dessert pieces)
PIECE_PRICES = {
    "Large":   35.0,
    "Medium":  25.0,
    "Regular": 15.0,
    "Small":   12.0,
}


async def seed_prices(rule_version_id: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)

    cursor = db[COLLECTION].find({
        "restaurantId": RESTAURANT_ID
    })

    updated = 0
    skipped = 0

    async for doc in cursor:
        sell_by_count = doc.get("sellByCount", False)
        update_data = {"updatedAt": now}

        if sell_by_count:
            size = doc.get("size", "Regular")
            price = PIECE_PRICES.get(size, 20.0)
            update_data["price"] = price
        else:
            category = doc.get("category")
            veg_non_veg = doc.get("vegNonVeg")
            tray_price = TRAY_PRICES.get((category, veg_non_veg))
            if not tray_price:
                print(f"No price mapping for {doc['itemCode']} — {category}/{veg_non_veg}")
                skipped += 1
                continue
            update_data["trayPrice"] = tray_price

        await db[COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": update_data}
        )
        updated += 1
        print(f"{doc['itemCode']} — {'piece' if sell_by_count else 'tray'} price set")

    print(f"Done! updated: {updated}, skipped: {skipped}")
    return {"updated": updated, "skipped": skipped}


async def create_indexes():
    db = get_db()
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("itemCode", 1), ("isActive", 1)]
    )
    await db[COLLECTION].create_index([("ruleVersionId", 1)])
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("category", 1), ("isActive", 1)]
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("category", 1), ("vegNonVeg", 1), ("sellByCount", 1)]
    )
    await db[COLLECTION].create_index([("importJobId", 1)])
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("itemCode", 1)],
        unique=True
    )
    print(f"Indexes created for {COLLECTION}")
