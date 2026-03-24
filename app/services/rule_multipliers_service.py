from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_db
from app.core.constants import MultiplierType, RESTAURANT_ID
from app.schemas.rule_multipliers import RuleMultiplierCreate, RuleMultiplierUpdate

COLLECTION = "rule_multipliers"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def create_multiplier(data: RuleMultiplierCreate) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = data.model_dump(exclude_none=True)
    doc["restaurantId"] = RESTAURANT_ID
    doc["createdAt"] = now
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def delete_multiplier(rule_version_id: str, multiplier_type: str, key: Optional[str]) -> int:
    db = get_db()
    filter_query = {
        "restaurantId": RESTAURANT_ID,
        "ruleVersionId": rule_version_id,
        "multiplierType": multiplier_type
    }

    print(f"filter_query: {filter_query}")
    count = await db[COLLECTION].count_documents(filter_query)
    print(f"matching docs: {count}")

    if key:
        filter_query["key"] = key
        result = await db[COLLECTION].find_one_and_delete(filter_query)
        return 1 if result else 0
    else:
        result = await db[COLLECTION].delete_many(filter_query)
        return result.deleted_count


async def get_multipliers_by_type(multiplier_type: str, is_active: Optional[bool] = True) -> list:
    db = get_db()
    query = {"restaurantId": RESTAURANT_ID}
    if multiplier_type:
        query["multiplierType"] = multiplier_type
    if is_active is not None:
        query["isActive"] = is_active
    cursor = db[COLLECTION].find(query)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def get_multiplier_by_key(multiplier_type: str, key: str) -> Optional[dict]:
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "multiplierType": multiplier_type,
        "key": key,
        "isActive": True
    })
    return _serialize(doc) if doc else None


async def update_multiplier(key: str, multiplier_type: str, data: RuleMultiplierUpdate) -> Optional[dict]:
    db = get_db()
    update_data = {k: v for k, v in data.model_dump(exclude_none=True).items() if v is not None}
    update_data["updatedAt"] = datetime.now(timezone.utc)

    if multiplier_type == "buffer":
        update_data.pop("multiplier", None)
    else:
        update_data.pop("bufferPercent", None)

    result = await db[COLLECTION].find_one_and_update(
        {
            "restaurantId": RESTAURANT_ID,
            "key": key,
            "multiplierType": multiplier_type
        },
        {"$set": update_data},
        return_document=True
    )
    return _serialize(result) if result else None


async def seed_default_multipliers(version_id: str):
    """
    Seed default multipliers during restaurant initial setup.
    Called once during onboarding.
    """
    defaults = [
        {"multiplierType": "event",    "key": "wedding",          "label": "Wedding",          "multiplier": 1.15},
        {"multiplierType": "event",    "key": "corporate_lunch",  "label": "Corporate Lunch",  "multiplier": 1.00},
        {"multiplierType": "event",    "key": "birthday_party",   "label": "Birthday Party",   "multiplier": 1.10},
        {"multiplierType": "event",    "key": "social_gathering", "label": "Social Gathering", "multiplier": 1.05},
        {"multiplierType": "service",  "key": "buffet",           "label": "Buffet",           "multiplier": 1.05},
        {"multiplierType": "service",  "key": "plated",           "label": "Plated",           "multiplier": 0.95},
        {"multiplierType": "service",  "key": "boxed_meal",       "label": "Boxed Meal",       "multiplier": 0.90},
        {"multiplierType": "audience", "key": "kids_factor",      "label": "Kids Factor",      "multiplier": 0.6},
        {"multiplierType": "buffer",   "key": "default_buffer",   "label": "Default Buffer",   "bufferPercent": 8},
    ]

    db = get_db()
    now = datetime.now(timezone.utc)
    for item in defaults:
        item["restaurantId"] = RESTAURANT_ID
        item["ruleVersionId"] = version_id
        item["isActive"] = True
        item["createdAt"] = now
        await db[COLLECTION].insert_one(item)

    print(f"Seeded {len(defaults)} default multipliers for {RESTAURANT_ID}")


async def create_indexes():
    db = get_db()
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("multiplierType", 1), ("isActive", 1)]
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("key", 1)]
    )
    await db[COLLECTION].create_index(
        [
            ("restaurantId", 1),
            ("ruleVersionId", 1),
            ("multiplierType", 1),
            ("key", 1)
        ],
        unique=True
    )
    print(f"Indexes created for {COLLECTION}")
