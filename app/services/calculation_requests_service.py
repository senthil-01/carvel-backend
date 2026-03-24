from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID
from app.schemas.calculation_requests import (
    CalculationRequestCreate,
    CalculationRequestStatusUpdate,
    RequestStatus,
    GuestDetailsStored,
)

COLLECTION = "calculation_requests"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_active_rule_version_id() -> str:
    db = get_db()
    doc = await db["rule_versions"].find_one(
        {"restaurantId": RESTAURANT_ID, "status": "active"},
        {"versionId": 1}
    )
    if not doc:
        raise ValueError(
            f"No active rule version found for restaurant '{RESTAURANT_ID}'. "
            "Publish a rule version before submitting requests."
        )
    return doc["versionId"]


async def _get_default_buffer() -> float:
    db = get_db()
    doc = await db["rule_multipliers"].find_one(
        {"restaurantId": RESTAURANT_ID, "multiplierType": "buffer", "isActive": True},
        {"bufferPercent": 1}
    )
    return float(doc["bufferPercent"]) if doc else 8.0


# ── Service functions ─────────────────────────────────────────────────────────

async def create_calculation_request(
    data: CalculationRequestCreate,
    requested_by: str
) -> dict:
    db  = get_db()
    now = datetime.now(timezone.utc)

    rule_version_id = await _get_active_rule_version_id()
    buffer_percent  = data.bufferPercent if data.bufferPercent is not None else await _get_default_buffer()
    request_id      = f"REQ-{uuid.uuid4().hex[:12].upper()}"

    doc = data.model_dump(exclude_none=False)
    doc["restaurantId"]   = RESTAURANT_ID
    doc["requestId"]      = request_id
    doc["ruleVersionId"]  = rule_version_id
    doc["requestedBy"]    = requested_by
    doc["bufferPercent"]  = buffer_percent
    doc["status"]         = RequestStatus.PENDING.value
    doc["normalizedAt"]   = None
    doc["createdAt"]      = now

    doc["requestChannel"]               = data.requestChannel.value
    doc["eventDetails"]["eventType"]    = data.eventDetails.eventType
    doc["eventDetails"]["serviceStyle"] = data.eventDetails.serviceStyle

    doc["guestDetails"] = GuestDetailsStored(**data.guestDetails.model_dump()).model_dump()

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    # ── Trigger engine immediately ────────────────────────────────────────────
    try:
        from app.services.calculation_results_service import run_calculation
        engine_result = await run_calculation(doc)

        has_custom_mode    = engine_result.get("hasCustomMode", False)
        has_remainder_flag = engine_result.get("hasRemainderFlag", False)

        if has_custom_mode or has_remainder_flag:
            # pending_review — result saved to calculation_results with flags
            await db[COLLECTION].update_one(
                {"requestId": request_id},
                {"$set": {"status": RequestStatus.PENDING_REVIEW.value}}
            )
            doc["status"] = RequestStatus.PENDING_REVIEW.value

        else:
            # clean result — already saved to calculation_results by engine
            await db[COLLECTION].update_one(
                {"requestId": request_id},
                {"$set": {"status": RequestStatus.COMPLETED.value}}
            )
            doc["status"] = RequestStatus.COMPLETED.value

    except Exception as e:
        await db[COLLECTION].update_one(
            {"requestId": request_id},
            {"$set": {"status": RequestStatus.FAILED.value}}
        )
        doc["status"] = RequestStatus.FAILED.value
        print(f"Engine failed for request {request_id}: {e}")
        raise

    return doc


async def get_request_by_id(request_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "requestId":    request_id
    })
    return _serialize(doc) if doc else None


async def get_all_requests(
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    exclude_voided: bool = False,
    page: int = 1,
    page_size: int = 20
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if status:
        query["status"] = status
    if exclude_voided:
        query["status"] = {"$ne": RequestStatus.VOIDED.value}
    if event_type:
        query["eventDetails.eventType"] = event_type

    date_filter: dict = {}
    if from_date:
        date_filter["$gte"] = from_date
    if to_date:
        date_filter["$lte"] = to_date
    if date_filter:
        query["eventDetails.eventDate"] = date_filter

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("createdAt", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def update_request_status(
    request_id: str,
    data: CalculationRequestStatusUpdate
) -> Optional[dict]:
    db = get_db()

    existing = await db[COLLECTION].find_one(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"status": 1}
    )
    if not existing:
        return None

    allowed_transitions = {
        RequestStatus.PENDING.value:        {RequestStatus.PROCESSING.value},
        RequestStatus.PROCESSING.value:     {RequestStatus.COMPLETED.value, RequestStatus.FAILED.value},
        RequestStatus.PENDING_REVIEW.value: {RequestStatus.COMPLETED.value, RequestStatus.VOIDED.value},
        RequestStatus.COMPLETED.value:      {RequestStatus.VOIDED.value},
    }
    if data.status.value not in allowed_transitions.get(existing["status"], set()):
        raise ValueError(
            f"Invalid transition: '{existing['status']}' → '{data.status.value}'"
        )

    update_fields: dict = {"status": data.status.value}
    if data.normalizedAt:
        update_fields["normalizedAt"] = data.normalizedAt

    result = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"$set": update_fields},
        return_document=True
    )
    return _serialize(result) if result else None


async def void_request(request_id: str) -> Optional[dict]:
    """
    Mark request as voided — customer left checkout without placing order.
    Also voids any pending override requests for this order.
    """
    db  = get_db()
    doc = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"$set": {"status": RequestStatus.VOIDED.value}},
        return_document=True
    )
    if doc:
        # void any pending override requests tied to this order
        await db["override_requests"].update_many(
            {
                "restaurantId":            RESTAURANT_ID,
                "impactedOn.requestId":    request_id,
                "status":                  "pending"
            },
            {"$set": {"status": "voided"}}
        )
    return _serialize(doc) if doc else None


async def get_pending_queue() -> list:
    db     = get_db()
    cursor = db[COLLECTION].find({
        "restaurantId": RESTAURANT_ID,
        "status":       RequestStatus.PENDING.value
    }).sort("createdAt", 1)

    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def create_indexes():
    db = get_db()

    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("createdAt", -1)],
        name="idx_restaurantId_createdAt_desc"
    )
    await db[COLLECTION].create_index(
        [("requestId", 1)],
        unique=True,
        name="idx_requestId_unique"
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("status", 1)],
        name="idx_restaurantId_status"
    )
    await db[COLLECTION].create_index(
        [("eventDetails.eventDate", 1)],
        name="idx_eventDetails_eventDate"
    )
    print(f"Indexes created for {COLLECTION}")