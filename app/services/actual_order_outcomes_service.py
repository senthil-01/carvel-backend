from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID
from app.schemas.actual_order_outcomes import ActualOrderOutcomeCreate

COLLECTION = "actual_order_outcomes"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_event_summary(request_id: str, result_summary: dict, guest_details: dict) -> dict:
    """Auto-fetch eventSummary from calculation_requests + result summary."""
    db = get_db()

    request_doc = await db["calculation_requests"].find_one(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"eventDetails": 1, "guestDetails": 1}
    )
    if not request_doc:
        return {}

    event_details = request_doc.get("eventDetails", {})
    guest_details = request_doc.get("guestDetails", {})

    return {
        "eventType":       event_details.get("eventType"),
        "serviceStyle":    event_details.get("serviceStyle"),
        "eventDate":       event_details.get("eventDate"),
        "guestCount":      guest_details.get("totalGuests"),
        "effectiveGuests": result_summary.get("effectiveGuests"),
    }


async def _fetch_recommended_trays(item_results: list, item_code: str) -> Optional[float]:
    """Fetch recommendedTrays for a specific item from already-fetched itemResults."""
    for item in item_results:
        if item.get("itemCode") == item_code:
            tray_result = item.get("trayResult", {})
            if tray_result:
                # total trays = L + M + S
                return (
                    tray_result.get("L", 0) +
                    tray_result.get("M", 0) +
                    tray_result.get("S", 0)
                )
            # Path 2 — piece count items
            return item.get("totalPieces")
    return None


async def _fetch_remainder_flag(request_id: str, item_code: str) -> Optional[dict]:
    """
    Fetch remainderFlag for a specific item from engineResult in calculation_requests.
    Only present for middle-threshold items — flagged to sales/ops and acknowledged.
    Provides insight for learning engine — remainder pattern per item+scenario.
    """
    db = get_db()

    request_doc = await db["calculation_requests"].find_one(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"engineResult": 1}
    )
    if not request_doc:
        return None

    engine_result = request_doc.get("engineResult", {})
    for item in engine_result.get("itemResults", []):
        if item.get("itemCode") == item_code:
            return item.get("remainderFlag")
    return None


# ── Service functions ─────────────────────────────────────────────────────────

async def create_outcome(
    data: ActualOrderOutcomeCreate,
    recorded_by: str,
) -> dict:
    db  = get_db()
    now = datetime.now(timezone.utc)

    # fetch result doc — primary source for requestId and ruleVersionId
    result_doc = await db["calculation_results"].find_one(
        {"restaurantId": RESTAURANT_ID, "resultId": data.resultId}
    )
    if not result_doc:
        raise ValueError(f"Calculation result '{data.resultId}' not found.")

    # auto-fetch from result doc — no separate DB calls needed
    request_id      = result_doc.get("requestId")
    rule_version_id = result_doc.get("ruleVersionId")
    result_summary  = result_doc.get("summary", {})
    item_results    = result_doc.get("itemResults", [])

    # validate all items from result are covered by staff input
    result_item_codes = {item["itemCode"] for item in item_results}
    input_item_codes  = {item.itemCode for item in data.itemOutcomes}
    missing           = result_item_codes - input_item_codes
    if missing:
        raise ValueError(
            f"Missing outcome for items: {', '.join(missing)}. "
            "All items in the order must have outcome recorded."
        )

    # auto-fetch eventSummary
    event_summary = await _fetch_event_summary(request_id, result_summary, {})
    outcome_id    = f"OUT-{uuid.uuid4().hex[:12].upper()}"

    # build itemOutcomes with auto-computed fields
    item_outcomes = []
    for item_input in data.itemOutcomes:
        recommended    = await _fetch_recommended_trays(item_results, item_input.itemCode)
        remainder_flag = await _fetch_remainder_flag(request_id, item_input.itemCode)

        # auto-compute manualAdjustment
        manual_adjustment = (
            recommended is not None and
            item_input.actualPreparedTrays != recommended
        )

        # auto-fill reason only when manualAdjustment is True and remainderFlag exists
        manual_adjustment_reason = None
        if manual_adjustment and remainder_flag:
            manual_adjustment_reason = remainder_flag.get("message")

        item_outcomes.append({
            "itemCode":               item_input.itemCode,
            "recommendedTrays":       recommended,
            "actualPreparedTrays":    item_input.actualPreparedTrays,
            "manualAdjustment":       manual_adjustment,
            "manualAdjustmentReason": manual_adjustment_reason,
            "leftoverPercentage":     item_input.leftoverPercentage,
            "shortageOccurred":       item_input.shortageOccurred,
            "shortageAmount":         item_input.shortageAmount,
            "customerSatisfaction":   item_input.customerSatisfaction.value if item_input.customerSatisfaction else None,
            "remainderFlag":          remainder_flag,
        })

    doc = {
        "outcomeId":           outcome_id,
        "requestId":           request_id,      # auto-fetched from result
        "resultId":            data.resultId,
        "restaurantId":        RESTAURANT_ID,
        "ruleVersionId":       rule_version_id, # auto-fetched from result
        "eventSummary":        event_summary,
        "itemOutcomes":        item_outcomes,
        "overallSatisfaction": data.overallSatisfaction.value if data.overallSatisfaction else None,
        "staffNotes":          data.staffNotes,
        "recordedBy":          recorded_by,
        "eventFulfilledAt":    data.eventFulfilledAt,
        "createdAt":           now,
    }

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    # increment ordersCollectedSoFar only for valid result statuses
    # final = clean order, overridden = staff adjusted — both are real confirmed orders
    calc_result = await db["calculation_results"].find_one(
        {"restaurantId": RESTAURANT_ID, "resultId": data.resultId},
        {"status": 1}
    )
    valid_statuses = {"final", "overridden", "pending_review"}
    if calc_result and calc_result.get("status") in valid_statuses:
        await db["learning_cycle_config"].update_one(
            {"restaurantId": RESTAURANT_ID},
            {"$inc": {"currentCycle.ordersCollectedSoFar": 1}}
        )

    return doc


async def get_outcome_by_id(outcome_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "outcomeId":    outcome_id
    })
    return _serialize(doc) if doc else None


async def get_outcome_by_result_id(result_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "resultId":     result_id
    })
    return _serialize(doc) if doc else None


async def get_all_outcomes(
    event_type: Optional[str] = None,
    service_style: Optional[str] = None,
    item_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if event_type:
        query["eventSummary.eventType"] = event_type
    if service_style:
        query["eventSummary.serviceStyle"] = service_style
    if item_code:
        query["itemOutcomes.itemCode"] = item_code

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("createdAt", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def create_indexes():
    db = get_db()

    # { restaurantId, createdAt: -1 } — learning engine reads recent first
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("createdAt", -1)],
        name="idx_restaurantId_createdAt_desc"
    )
    # { resultId } — primary link from result to outcome
    await db[COLLECTION].create_index(
        [("resultId", 1)],
        name="idx_resultId"
    )
    # { eventSummary.eventType, eventSummary.serviceStyle } — learning engine segmentation
    await db[COLLECTION].create_index(
        [("eventSummary.eventType", 1), ("eventSummary.serviceStyle", 1)],
        name="idx_eventType_serviceStyle"
    )
    # { itemOutcomes.itemCode } — item-level pattern analysis
    await db[COLLECTION].create_index(
        [("itemOutcomes.itemCode", 1)],
        name="idx_itemOutcomes_itemCode"
    )
    print(f"Indexes created for {COLLECTION}")