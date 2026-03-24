from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_db
from app.core.constants import VersionStatus, VersionSource, RESTAURANT_ID
from app.schemas.rule_versions import RuleVersionCreate

COLLECTION = "rule_versions"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def _get_next_version_number() -> int:
    db = get_db()
    last = await db[COLLECTION].find_one(
        {"restaurantId": RESTAURANT_ID},
        sort=[("versionNumber", -1)]
    )
    return (last["versionNumber"] + 1) if last else 1


async def _get_active_version_id() -> Optional[str]:
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "status": VersionStatus.ACTIVE
    })
    return doc["versionId"] if doc else None


async def create_version(data: RuleVersionCreate) -> dict:
    """
    Creates a new rule version in DRAFT status.
    Auto-increments versionNumber.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    version_number = await _get_next_version_number()
    version_id = f"rv_{RESTAURANT_ID}_{version_number:03d}"
    previous_version_id = await _get_active_version_id()

    doc = data.model_dump()
    doc["restaurantId"] = RESTAURANT_ID
    doc["versionId"] = version_id
    doc["versionNumber"] = version_number
    doc["status"] = VersionStatus.DRAFT
    doc["previousVersionId"] = previous_version_id
    doc["activatedAt"] = None
    doc["deactivatedAt"] = None
    doc["publishedAt"] = now
    doc["createdAt"] = now

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def activate_version(version_id: str) -> dict:
    """
    Activates a draft version.
    Archives the current active version first.
    Only ONE active version per restaurant at any time.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    # Archive current active version
    await db[COLLECTION].update_many(
        {"restaurantId": RESTAURANT_ID, "status": VersionStatus.ACTIVE},
        {"$set": {
            "status": VersionStatus.ARCHIVED,
            "deactivatedAt": now
        }}
    )

    # Activate the new version
    result = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "versionId": version_id},
        {"$set": {
            "status": VersionStatus.ACTIVE,
            "activatedAt": now
        }},
        return_document=True
    )
    return _serialize(result)


async def rollback_version(version_id: str) -> dict:
    """
    Rolls back to a previous archived version.
    Archives the current active version.
    """
    return await activate_version(version_id)


async def get_active_version() -> Optional[dict]:
    """Get the currently active rule version. Called by engine on every calculation."""
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "status": VersionStatus.ACTIVE
    })
    return _serialize(doc) if doc else None


async def get_all_versions() -> list:
    db = get_db()
    cursor = db[COLLECTION].find(
        {"restaurantId": RESTAURANT_ID},
        sort=[("versionNumber", -1)]
    )
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def get_version_by_id(version_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "versionId": version_id
    })
    return _serialize(doc) if doc else None


async def create_indexes():
    db = get_db()
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("status", 1)]
    )
    await db[COLLECTION].create_index([("versionId", 1)], unique=True)
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("versionNumber", 1)]
    )
    print(f"Indexes created for {COLLECTION}")
