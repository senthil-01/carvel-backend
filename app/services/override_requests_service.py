from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID, OverrideStatus
from app.schemas.override_requests import OverrideRequestCreate

COLLECTION = "override_requests"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def create_override_request(
    data: OverrideRequestCreate,
    requested_by: str,
    requested_by_role: str,
) -> dict:
    db  = get_db()
    now = datetime.now(timezone.utc)

    override_request_id = f"OVR-{uuid.uuid4().hex[:12].upper()}"

    doc = data.model_dump()
    doc["overrideRequestId"] = override_request_id
    doc["restaurantId"]      = RESTAURANT_ID
    doc["requestedBy"]       = requested_by
    doc["requestedByRole"]   = requested_by_role
    doc["requestedDate"]     = now
    doc["status"]            = OverrideStatus.PENDING.value
    doc["createdAt"]         = now
    doc["updatedAt"]         = now

    # serialize enums
    doc["overrideType"] = data.overrideType.value
    doc["reason"]       = data.reason.value
    doc["impactedOn"]   = data.impactedOn.model_dump()

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def get_override_request_by_id(override_request_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId":      RESTAURANT_ID,
        "overrideRequestId": override_request_id
    })
    return _serialize(doc) if doc else None


async def get_all_override_requests(
    status: Optional[str] = None,
    override_type: Optional[str] = None,
    item_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if status:
        query["status"] = status
    if override_type:
        query["overrideType"] = override_type
    if item_code:
        query["impactedOn.itemCode"] = item_code

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("requestedDate", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def create_indexes():
    db = get_db()

    # { restaurantId, status } — listing pending requests
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("status", 1)],
        name="idx_restaurantId_status"
    )
    # { overrideRequestId } unique — referenced by Collection 7
    await db[COLLECTION].create_index(
        [("overrideRequestId", 1)],
        unique=True,
        name="idx_overrideRequestId_unique"
    )
    # { impactedOn.resultId } — link back to calculation result
    await db[COLLECTION].create_index(
        [("impactedOn.resultId", 1)],
        name="idx_impactedOn_resultId"
    )
    # { impactedOn.itemCode, restaurantId } — item-level override history
    await db[COLLECTION].create_index(
        [("impactedOn.itemCode", 1), ("restaurantId", 1)],
        name="idx_impactedOn_itemCode"
    )
    print(f"Indexes created for {COLLECTION}")
