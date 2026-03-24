from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID
from app.schemas.calculation_results import ResultStatus

COLLECTION = "calculation_results"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Internal helpers — fetch multipliers ─────────────────────────────────────

async def _get_kids_factor() -> float:
    db  = get_db()
    doc = await db["rule_multipliers"].find_one(
        {"restaurantId": RESTAURANT_ID, "multiplierType": "audience", "isActive": True},
        {"multiplier": 1}
    )
    return float(doc["multiplier"]) if doc else 0.6


async def _get_event_multiplier(event_type: str) -> float:
    db  = get_db()
    doc = await db["rule_multipliers"].find_one(
        {"restaurantId": RESTAURANT_ID, "multiplierType": "event", "key": event_type, "isActive": True},
        {"multiplier": 1}
    )
    return float(doc["multiplier"]) if doc else 1.0


async def _get_service_multiplier(service_style: str) -> float:
    db  = get_db()
    doc = await db["rule_multipliers"].find_one(
        {"restaurantId": RESTAURANT_ID, "multiplierType": "service", "key": service_style, "isActive": True},
        {"multiplier": 1}
    )
    return float(doc["multiplier"]) if doc else 1.0


async def _get_menu_item(item_code: str) -> Optional[dict]:
    db  = get_db()
    doc = await db["menu_item_rules"].find_one({
        "restaurantId": RESTAURANT_ID,
        "itemCode":     item_code,
        "isActive":     True
    })
    return doc


# ── Scenario detection ────────────────────────────────────────────────────────

def _detect_scenario(category: str, all_items: list, item_rule: dict, item_rules_map: dict = {}) -> Optional[str]:
    if category == "Rice":
        rice_count  = len([i for i in all_items if i["category"] == "Rice"])
        bread_count = len([i for i in all_items if i["category"] == "Bread"])
        # try exact combo first
        if rice_count == 2 and bread_count == 1:
            scenario_key = "2 rice and 1 bread"
        else:
            # fall back to own rice count only
            scenario_key = f"{rice_count} rice"

    elif category == "Bread":
        rice_count  = len([i for i in all_items if i["category"] == "Rice"])
        bread_count = len([i for i in all_items if i["category"] == "Bread"])
        # try exact combo first
        if bread_count == 1 and rice_count == 1:
            scenario_key = "1 bread and 1 rice"
        elif bread_count == 1 and rice_count == 2:
            scenario_key = "1 bread and 2 rice"
        else:
            # fall back to own bread count only
            scenario_key = f"{bread_count} bread"

    else:
        # count only same sellByCount type — use item_rules_map to get sellByCount from DB
        is_count_item = item_rule.get("sellByCount", False)
        count         = len([
            i for i in all_items
            if i["category"] == category
            and item_rules_map.get(i["itemCode"], {}).get("sellByCount", False) == is_count_item
        ])
        category_lower = category.lower()
        scenario_key   = f"{count} {category_lower}"

    if item_rule.get("sellByCount"):
        exists = scenario_key in (item_rule.get("countScenarios") or {})
    else:
        exists = scenario_key in (item_rule.get("scenarios") or {})

    return scenario_key if exists else None


# ── Tray fitting ──────────────────────────────────────────────────────────────

def _fit_trays(
    final_demand: float,
    S: float, M: float, L: float,
    effective_guests: float,
    buffer_percent: float,
    request_id: str,
    item_code: str,
    menu_name: str,
) -> dict:
    remaining = final_demand
    l_count = m_count = s_count = 0
    remainder_flag = None

    while L <= remaining:
        l_count   += 1
        remaining -= L

    while M <= remaining:
        m_count   += 1
        remaining -= M

    while S <= remaining:
        s_count   += 1
        remaining -= S

    if remaining > 0:
        s_percentage     = (remaining / S) * 100
        guest_percentage = (remaining / effective_guests) * 100

        if s_percentage >= 80:
            s_count += 1

        elif guest_percentage >= buffer_percent:
            remainder_flag = {
                "requestId":         request_id,
                "itemCode":          item_code,
                "menuName":          menu_name,
                "remainingGuests":   round(remaining, 2),
                "guestPercentage":   round(guest_percentage, 2),
                "smallTrayCapacity": S,
                "sPercentage":       round(s_percentage, 2),
                "message": (
                    f"{round(remaining, 2)} guests uncovered "
                    f"({round(guest_percentage, 2)}% of total guests). "
                    f"Small tray covers {S} guests — only {round(s_percentage, 2)}% would be used. "
                    f"Sales/ops review needed."
                ),
                "acknowledged":   False,
                "acknowledgedBy": None,
                "acknowledgedAt": None,
            }

    return {"L": l_count, "M": m_count, "S": s_count, "remainderFlag": remainder_flag}


# ── Path 1 — Sell by Tray ─────────────────────────────────────────────────────

def _calculate_path1(
    item: dict, scenario_key: str,
    effective_guests: float, adjusted_demand: float,
    final_demand: float, buffer_percent: float, request_id: str,
) -> dict:
    spread      = item["scenarios"][scenario_key]["spread"]
    S, M, L     = spread["S"], spread["M"], spread["L"]
    tray_result = _fit_trays(
        final_demand, S, M, L,
        effective_guests, buffer_percent,
        request_id, item["itemCode"], item["menuName"]
    )
    return {
        "itemCode":      item["itemCode"],
        "menuName":      item["menuName"],
        "category":      item["category"],
        "vegNonVeg":     item["vegNonVeg"],
        "sellByCount":   False,
        "customMode":    False,
        "scenarioUsed":  scenario_key,
        "trayResult":    {"L": tray_result["L"], "M": tray_result["M"], "S": tray_result["S"]},
        "remainderFlag": tray_result["remainderFlag"],
        "trace": {
            "step1_effectiveGuests": effective_guests,
            "step2_adjustedDemand":  round(adjusted_demand, 4),
            "step3_finalDemand":     round(final_demand, 4),
            "step4_scenarioUsed":    scenario_key,
            "step4_spread":          spread,
            "step5_result":          {"L": tray_result["L"], "M": tray_result["M"], "S": tray_result["S"]},
        }
    }


# ── Path 2 — Sell by Count ────────────────────────────────────────────────────

def _calculate_path2(item: dict, scenario_key: str, effective_guests: float) -> dict:
    pieces_per_person = item["countScenarios"][scenario_key]["piecesPerPerson"]
    total_pieces      = round(effective_guests * pieces_per_person, 2)
    return {
        "itemCode":     item["itemCode"],
        "menuName":     item["menuName"],
        "category":     item["category"],
        "vegNonVeg":    item["vegNonVeg"],
        "sellByCount":  True,
        "customMode":   False,
        "scenarioUsed": scenario_key,
        "totalPieces":  total_pieces,
        "trace": {
            "step1_effectiveGuests": effective_guests,
            "step2_scenarioUsed":    scenario_key,
            "step2_piecesPerPerson": pieces_per_person,
            "step3_totalPieces":     total_pieces,
        }
    }


# ── Auto-create override request for custom mode ──────────────────────────────

async def _auto_create_override_request(
    request_id: str,
    item_code: str,
    menu_name: str,
    old_value: dict,
    new_value: dict,
    requested_by: str,
    requested_by_role: str,
) -> None:
    db  = get_db()
    now = datetime.now(timezone.utc)

    override_request_id = f"OVR-{uuid.uuid4().hex[:12].upper()}"
    doc = {
        "overrideRequestId": override_request_id,
        "restaurantId":      RESTAURANT_ID,
        "requestedBy":       requested_by,
        "requestedByRole":   requested_by_role,
        "requestedDate":     now,
        "status":            "pending",
        "overrideType":      "calculation",
        "impactedOn": {
            "resultId":  None,
            "requestId": request_id,
            "itemCode":  item_code,
            "menuName":  menu_name,
            "ruleField": None,
        },
        "oldValue":           old_value,
        "newValue":           new_value,
        "reason":             "new_item_no_history",
        "justificationNotes": "Manual entry — no matching scenario found for this item. Sales/ops override applied.",
        "effectiveFrom":      now,
        "effectiveTo":        None,
        "createdAt":          now,
        "updatedAt":          now,
    }
    await db["override_requests"].insert_one(doc)


# ── Price calculation helper ─────────────────────────────────────────────────

def _get_line_total(item_result: dict, item_rule: dict) -> float:
    """Calculate line total for a single item from trayPrice or piece price."""
    if item_result.get("customMode"):
        return 0.0  # unknown — pending manual entry

    if item_rule.get("sellByCount"):
        price        = item_rule.get("price", 0) or 0
        total_pieces = item_result.get("totalPieces", 0) or 0
        return round(price * total_pieces, 2)

    tray_result = item_result.get("trayResult", {}) or {}
    tray_price  = item_rule.get("trayPrice", {}) or {}
    return round(
        (tray_result.get("L", 0) * (tray_price.get("L") or 0)) +
        (tray_result.get("M", 0) * (tray_price.get("M") or 0)) +
        (tray_result.get("S", 0) * (tray_price.get("S") or 0)),
        2
    )


# ── Main engine ───────────────────────────────────────────────────────────────

async def run_calculation(request_doc: dict) -> dict:
    """
    Main calculation engine.
    Always saves result to calculation_results immediately.
    hasCustomMode / hasRemainderFlag flags indicate pending review items.
    """
    db             = get_db()
    guest_details  = request_doc["guestDetails"]
    event_details  = request_doc["eventDetails"]
    menu_items     = request_doc["menuItems"]
    buffer_percent = request_doc["bufferPercent"]
    event_type     = event_details["eventType"]
    service_style  = event_details["serviceStyle"]
    request_id     = request_doc["requestId"]

    kids_factor      = await _get_kids_factor()
    effective_guests = guest_details["adultCount"] + (guest_details["kidsCount"] * kids_factor)

    event_multiplier   = await _get_event_multiplier(event_type)
    service_multiplier = await _get_service_multiplier(service_style)
    adjusted_demand    = effective_guests * event_multiplier * service_multiplier
    final_demand       = adjusted_demand * (1 + buffer_percent / 100)

    item_results       = []
    has_custom_mode    = False
    has_remainder_flag = False

    # ── Pre-fetch ALL item rules before loop for accurate scenario detection ──
    item_rules_map: dict = {}
    for menu_item in menu_items:
        rule = await _get_menu_item(menu_item["itemCode"])
        if rule:
            item_rules_map[menu_item["itemCode"]] = rule

    for menu_item in menu_items:
        item_code = menu_item["itemCode"]
        category  = menu_item["category"]

        item_rule = item_rules_map.get(item_code)
        if not item_rule:
            item_results.append({
                "itemCode":   item_code,
                "menuName":   item_code,
                "category":   category,
                "vegNonVeg":  menu_item["vegNonVeg"],
                "customMode": True,
                "message":    f"Item '{item_code}' not found in menu rules."
            })
            has_custom_mode = True
            continue

        scenario_key = _detect_scenario(category, menu_items, item_rule, item_rules_map)

        if scenario_key is None:
            count = len([i for i in menu_items if i["category"] == category])
            item_results.append({
                "itemCode":    item_rule["itemCode"],
                "menuName":    item_rule["menuName"],
                "category":    category,
                "vegNonVeg":   item_rule["vegNonVeg"],
                "sellByCount": item_rule.get("sellByCount"),
                "customMode":  True,
                "message":     f"No matching scenario for {count} {category.lower()} dishes. Manual entry required.",
            })
            has_custom_mode = True
            continue

        if not item_rule.get("sellByCount"):
            result = _calculate_path1(
                item_rule, scenario_key,
                effective_guests, adjusted_demand, final_demand,
                buffer_percent, request_id,
            )
            if result.get("remainderFlag"):
                has_remainder_flag = True
        else:
            result = _calculate_path2(item_rule, scenario_key, effective_guests)

        item_results.append(result)

    # ── Calculate totalAmount from item results ───────────────────────────────
    total_amount = round(sum(
        _get_line_total(item, item_rules_map.get(item["itemCode"], {}))
        for item in item_results
    ), 2)

    # ── Always save to calculation_results immediately ────────────────────────
    result_id = f"RES-{uuid.uuid4().hex[:12].upper()}"
    now       = datetime.now(timezone.utc)

    doc = {
        "resultId":           result_id,
        "requestId":          request_id,
        "restaurantId":       RESTAURANT_ID,
        "ruleVersionId":      request_doc["ruleVersionId"],
        "summary": {
            "effectiveGuests":   round(effective_guests, 4),
            "kidsFactor":        kids_factor,
            "eventType":         event_type,
            "serviceStyle":      service_style,
            "eventMultiplier":   event_multiplier,
            "serviceMultiplier": service_multiplier,
            "bufferApplied":     buffer_percent,
        },
        "itemResults":         item_results,
        "totalAmount":         total_amount,
        "hasCustomMode":       has_custom_mode,
        "hasRemainderFlag":    has_remainder_flag,
        "originalHasCustomMode":    has_custom_mode,
        "originalHasRemainderFlag": has_remainder_flag,
        "overrideApplied":     False,
        "overrideId":          None,
        "status":              ResultStatus.PENDING_REVIEW.value if (has_custom_mode or has_remainder_flag) else ResultStatus.FINAL.value,
        "calculatedAt":        now,
        "createdAt":           now,
    }

    await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(doc.get("_id", ""))

    return {
        "hasCustomMode":    has_custom_mode,
        "hasRemainderFlag": has_remainder_flag,
        "resultId":         result_id,
    }


# ── Manual entry — sales/ops resolves custom mode items ──────────────────────

async def update_manual_entry(
    request_id: str,
    item_code: str,
    requested_by: str,
    requested_by_role: str,
    tray_result: Optional[dict] = None,
    total_pieces: Optional[float] = None,
) -> Optional[dict]:
    db  = get_db()
    now = datetime.now(timezone.utc)

    result_doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "requestId":    request_id
    })
    if not result_doc:
        return None

    item_results = result_doc.get("itemResults", [])
    item_found   = False
    menu_name    = item_code
    summary      = result_doc.get("summary", {})

    for item in item_results:
        if item["itemCode"] == item_code and item.get("customMode"):
            item["customMode"] = False
            menu_name          = item.get("menuName", item_code)

            if item.get("trayResult"):
                old_value = item["trayResult"]
            elif item.get("totalPieces") is not None:
                old_value = {"totalPieces": item["totalPieces"]}
            else:
                old_value = {}

            if tray_result:
                item["trayResult"] = tray_result
                new_value          = tray_result
            if total_pieces is not None:
                item["totalPieces"] = total_pieces
                new_value           = {"totalPieces": total_pieces}

            # build trace from summary
            effective_guests = summary.get("effectiveGuests", 0)
            adjusted_demand  = round(
                effective_guests *
                summary.get("eventMultiplier", 1.0) *
                summary.get("serviceMultiplier", 1.0), 4
            )
            final_demand = round(adjusted_demand * (1 + summary.get("bufferApplied", 0) / 100), 4)

            item["trace"] = {
                "step1_effectiveGuests": effective_guests,
                "step2_adjustedDemand":  adjusted_demand,
                "step3_finalDemand":     final_demand,
                "step4_scenarioUsed":    None,
                "step4_spread":          None,
                "step5_result":          tray_result or {"totalPieces": total_pieces},
                "manualEntry":           True,
            }

            item["manualEntry"] = True
            item_found          = True
            break

    if not item_found:
        return None

    await _auto_create_override_request(
        request_id=request_id,
        item_code=item_code,
        menu_name=menu_name,
        old_value=old_value,
        new_value=new_value,
        requested_by=requested_by,
        requested_by_role=requested_by_role,
    )

    still_custom    = any(i.get("customMode") for i in item_results)
    still_remainder = result_doc.get("hasRemainderFlag", False)

    # recalculate totalAmount — fetch prices for resolved items
    new_total = 0.0
    for item in item_results:
        if item.get("customMode"):
            continue
        item_rule = await _get_menu_item(item["itemCode"])
        if item_rule:
            new_total += _get_line_total(item, item_rule)
    new_total = round(new_total, 2)

    result_status = "overridden" if (not still_custom and not still_remainder) else result_doc.get("status", "final")

    await db[COLLECTION].update_one(
        {"requestId": request_id},
        {"$set": {
            "itemResults":   item_results,
            "hasCustomMode": still_custom,
            "totalAmount":   new_total,
            "status":        result_status,
        }}
    )

    # update request status
    if not still_custom and not still_remainder:
        await db["calculation_requests"].update_one(
            {"requestId": request_id},
            {"$set": {"status": "completed"}}
        )

    updated = await db[COLLECTION].find_one({"requestId": request_id})
    return _serialize(updated)


# ── Acknowledge remainder flag ────────────────────────────────────────────────

async def acknowledge_remainder(
    request_id: str,
    item_code: str,
    acknowledged_by: str,
    extra_amount_added: Optional[float] = None,
    extra_amount_note: Optional[str] = None,
) -> Optional[dict]:
    db  = get_db()
    now = datetime.now(timezone.utc)

    result_doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "requestId":    request_id
    })
    if not result_doc:
        return None

    item_results = result_doc.get("itemResults", [])
    item_found   = False

    for item in item_results:
        if item.get("itemCode") == item_code and item.get("remainderFlag"):
            item["remainderFlag"]["acknowledged"]      = True
            item["remainderFlag"]["acknowledgedBy"]     = acknowledged_by
            item["remainderFlag"]["acknowledgedAt"]     = now
            item["remainderFlag"]["extraAmountAdded"]   = extra_amount_added
            item["remainderFlag"]["extraAmountNote"]    = extra_amount_note
            item_found = True
            break

    if not item_found:
        return None

    still_pending = any(
        item.get("remainderFlag") and not item["remainderFlag"].get("acknowledged")
        for item in item_results
    )
    still_custom = result_doc.get("hasCustomMode", False)

    # update totalAmount — add extraAmountAdded if provided
    current_total = result_doc.get("totalAmount", 0) or 0
    if extra_amount_added:
        current_total = round(current_total + extra_amount_added, 2)

    result_status = "overridden" if (not still_custom and not still_pending) else result_doc.get("status", "final")

    await db[COLLECTION].update_one(
        {"requestId": request_id},
        {"$set": {
            "itemResults":      item_results,
            "hasRemainderFlag": still_pending,
            "totalAmount":      current_total,
            "status":           result_status,
        }}
    )

    if not still_custom and not still_pending:
        await db["calculation_requests"].update_one(
            {"requestId": request_id},
            {"$set": {"status": "completed"}}
        )

    updated = await db[COLLECTION].find_one({"requestId": request_id})
    return _serialize(updated)


# ── GET functions ─────────────────────────────────────────────────────────────

async def void_result_by_request_id(request_id: str) -> Optional[dict]:
    """Mark result as voided — customer left checkout without placing order."""
    db  = get_db()
    doc = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"$set": {"status": ResultStatus.VOIDED.value}},
        return_document=True
    )
    return _serialize(doc) if doc else None


async def update_result_status_by_request_id(request_id: str, status: str) -> Optional[dict]:
    """
    Update calculation_results status using requestId.
    Called by CheckoutPage when customer confirms order.
    final → order_placed → learning engine reads this.
    """
    db  = get_db()
    doc = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID, "requestId": request_id},
        {"$set": {"status": status}},
        return_document=True
    )
    return _serialize(doc) if doc else None


async def get_result_by_id(result_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "resultId":     result_id
    })
    return _serialize(doc) if doc else None


async def get_result_by_request_id(request_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "requestId":    request_id
    })
    return _serialize(doc) if doc else None


async def get_all_results(
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    has_custom_mode: Optional[bool] = None,
    has_remainder_flag: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if status:
        query["status"] = status
    if event_type:
        query["summary.eventType"] = event_type
    if has_custom_mode is not None:
        query["hasCustomMode"] = has_custom_mode
    if has_remainder_flag is not None:
        query["hasRemainderFlag"] = has_remainder_flag

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("calculatedAt", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def create_indexes():
    db = get_db()

    await db[COLLECTION].create_index(
        [("requestId", 1)],
        unique=True,
        name="idx_requestId_unique"
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("calculatedAt", -1)],
        name="idx_restaurantId_calculatedAt_desc"
    )
    await db[COLLECTION].create_index(
        [("ruleVersionId", 1)],
        name="idx_ruleVersionId"
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("summary.eventType", 1)],
        name="idx_restaurantId_eventType"
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("hasCustomMode", 1)],
        name="idx_restaurantId_hasCustomMode"
    )
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("hasRemainderFlag", 1)],
        name="idx_restaurantId_hasRemainderFlag"
    )
    print(f"Indexes created for {COLLECTION}")