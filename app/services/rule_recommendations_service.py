from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID, VersionSource
from app.schemas.rule_recommendations import RuleRecommendationCreate, RecommendationStatus

COLLECTION = "rule_recommendations"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Learning engine analysis helpers ─────────────────────────────────────────

async def _get_cycle_config() -> dict:
    """Fetch learning cycle config — thresholds and current cycle info."""
    db  = get_db()
    doc = await db["learning_cycle_config"].find_one({"restaurantId": RESTAURANT_ID})
    return doc or {}


async def _get_active_rule_version_id() -> Optional[str]:
    db  = get_db()
    doc = await db["rule_versions"].find_one(
        {"restaurantId": RESTAURANT_ID, "status": "active"},
        {"versionId": 1}
    )
    return doc["versionId"] if doc else None


def _determine_learning_stage(orders_analysed: int, min_orders: int) -> str:
    """
    Stage determined by orders analysed vs configurable minimum threshold.
    min_orders comes from learning_cycle_config.minimumOrderCount
    """
    if orders_analysed < min_orders:
        return "stage_1"
    elif orders_analysed < min_orders * 3:
        return "stage_2"
    else:
        return "stage_3"


def _generate_reason(
    shortage_frequency: float,
    avg_leftover: float,
    avg_variance: float,
) -> str:
    """Generate human-readable reason from analytics patterns."""
    if shortage_frequency >= 20:
        return f"Shortage detected in {round(shortage_frequency, 1)}% of similar events"
    elif avg_leftover >= 30:
        return f"Average leftover {round(avg_leftover, 1)}% — spread values may be too high"
    elif avg_variance >= 15:
        return f"Actual prepared {round(avg_variance, 1)}% higher than recommended consistently"
    else:
        return f"Pattern detected across {round(avg_variance, 1)}% variance in actual vs recommended"


async def _analyse_item_segment(
    item_code: str,
    segment: str,
    cycle_start: datetime,
    cycle_end: datetime,
) -> Optional[dict]:
    """
    Analyse actual_order_outcomes for a specific item+segment combination.
    Returns analytics dict or None if insufficient data.
    """
    db = get_db()

    # parse segment — e.g. "wedding + buffet"
    parts        = [p.strip() for p in segment.split("+")]
    event_type   = parts[0] if len(parts) > 0 else None
    service_style = parts[1] if len(parts) > 1 else None

    query: dict = {
        "restaurantId":           RESTAURANT_ID,
        "itemOutcomes.itemCode":  item_code,
        "createdAt":              {"$gte": cycle_start, "$lte": cycle_end},
    }
    if event_type:
        query["eventSummary.eventType"] = event_type
    if service_style:
        query["eventSummary.serviceStyle"] = service_style

    cursor = db["actual_order_outcomes"].find(query)
    docs   = await cursor.to_list(length=None)

    if not docs:
        return None

    # fetch result statuses — overridden orders counted twice (more weight)
    result_ids = [d.get("resultId") for d in docs if d.get("resultId")]
    result_status = {}
    if result_ids:
        r_cursor = db["calculation_results"].find(
            {"resultId": {"$in": result_ids}},
            {"resultId": 1, "status": 1}
        )
        async for r in r_cursor:
            result_status[r["resultId"]] = r.get("status", "final")

    # weight overridden orders — count them twice
    weighted_docs = []
    for doc in docs:
        weighted_docs.append(doc)
        if result_status.get(doc.get("resultId")) == "overridden":
            weighted_docs.append(doc)  # count twice

    # extract item-level data using weighted docs
    leftovers   = []
    shortages   = []
    variances   = []
    shortage_count = 0

    for doc in weighted_docs:
        for item in doc.get("itemOutcomes", []):
            if item.get("itemCode") == item_code:
                leftovers.append(item.get("leftoverPercentage", 0))
                if item.get("shortageOccurred"):
                    shortage_count += 1
                recommended = item.get("recommendedTrays", 0) or 0
                actual      = item.get("actualPreparedTrays", 0) or 0
                if recommended > 0:
                    variance = abs(actual - recommended) / recommended * 100
                    variances.append(variance)

    real_order_count     = len(docs)          # real count for minimum check
    weighted_count       = len(weighted_docs) # weighted count for averages
    avg_leftover         = sum(leftovers) / len(leftovers) if leftovers else 0
    shortage_frequency   = (shortage_count / real_order_count * 100) if real_order_count else 0
    avg_variance         = sum(variances) / len(variances) if variances else 0

    return {
        "totalOrders":               real_order_count,    # real count
        "weightedOrders":            weighted_count,      # weighted count
        "avgLeftoverPct":            round(avg_leftover, 2),
        "shortageFrequencyPct":      round(shortage_frequency, 2),
        "avgActualVsRecommendedVariance": round(avg_variance, 2),
        "estimatedImpact":           "Reducing shortage risk and food waste",
    }
    for item in doc.get("itemOutcomes", []):
            if item.get("itemCode") == item_code:
                leftovers.append(item.get("leftoverPercentage", 0))
                if item.get("shortageOccurred"):
                    shortage_count += 1
                recommended = item.get("recommendedTrays", 0) or 0
                actual      = item.get("actualPreparedTrays", 0) or 0
                if recommended > 0:
                    variance = abs(actual - recommended) / recommended * 100
                    variances.append(variance)

    total_orders         = len(weighted_docs)
    avg_leftover         = sum(leftovers) / len(leftovers) if leftovers else 0
    shortage_frequency   = (shortage_count / total_orders * 100) if total_orders else 0
    avg_variance         = sum(variances) / len(variances) if variances else 0

    return {
        "totalOrders":               total_orders,
        "avgLeftoverPct":            round(avg_leftover, 2),
        "shortageFrequencyPct":      round(shortage_frequency, 2),
        "avgActualVsRecommendedVariance": round(avg_variance, 2),
        "estimatedImpact":           "Reducing shortage risk and food waste",
    }


# ── Main engine — run learning analysis ──────────────────────────────────────

async def run_learning_engine(cycle_id: str, cycle_start: datetime, cycle_end: datetime) -> int:
    """
    Main learning engine — called by background job when bothConditionsMet.
    Analyses actual_order_outcomes and generates recommendations.
    Returns count of recommendations generated.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    # ── Guard — prevent duplicate runs same cycle ─────────────────────────────
    config = await _get_cycle_config()
    if config.get("currentCycle", {}).get("recommendationsGenerated"):
        return 0  # already ran this cycle
    min_orders      = config.get("minimumOrderCount", 30)
    rule_version_id = await _get_active_rule_version_id()
    orders_analysed = config.get("currentCycle", {}).get("ordersCollectedSoFar", 0)
    learning_stage  = _determine_learning_stage(orders_analysed, min_orders)

    # get all unique item+segment combinations from outcomes in cycle
    # prioritize overridden results — most valuable data (human adjustment + actual outcome)
    cursor = db["actual_order_outcomes"].find({
        "restaurantId": RESTAURANT_ID,
        "createdAt":    {"$gte": cycle_start, "$lte": cycle_end}
    })
    docs = await cursor.to_list(length=None)

    # fetch result statuses to weight overridden orders higher
    result_ids    = [d.get("resultId") for d in docs if d.get("resultId")]
    result_status = {}
    if result_ids:
        r_cursor = db["calculation_results"].find(
            {"resultId": {"$in": result_ids}},
            {"resultId": 1, "status": 1}
        )
        async for r in r_cursor:
            result_status[r["resultId"]] = r.get("status", "final")

    # sort — overridden first, then final
    docs.sort(key=lambda d: 0 if result_status.get(d.get("resultId")) == "overridden" else 1)

    # build unique item+segment pairs
    item_segments = set()
    for doc in docs:
        event_type    = doc.get("eventSummary", {}).get("eventType", "")
        service_style = doc.get("eventSummary", {}).get("serviceStyle", "")
        segment       = f"{event_type} + {service_style}"
        for item in doc.get("itemOutcomes", []):
            item_segments.add((item["itemCode"], segment))

    recommendations_count = 0

    for item_code, segment in item_segments:

        # duplicate check — skip if already exists for same item+segment+cycle
        existing = await db[COLLECTION].find_one({
            "restaurantId": RESTAURANT_ID,
            "itemCode":     item_code,
            "segment":      segment,
            "cycleId":      cycle_id,
        })
        if existing:
            continue

        # analyse this item+segment combination
        analytics = await _analyse_item_segment(item_code, segment, cycle_start, cycle_end)
        if not analytics or analytics["totalOrders"] < 3:  # use real count
            continue  # not enough data for this combination

        # fetch current rule from menu_item_rules
        item_rule = await db["menu_item_rules"].find_one({
            "restaurantId": RESTAURANT_ID,
            "itemCode":     item_code,
            "isActive":     True,
        })
        if not item_rule:
            continue

        menu_name = item_rule.get("menuName", item_code)

        # generate reason
        reason = _generate_reason(
            analytics["shortageFrequencyPct"],
            analytics["avgLeftoverPct"],
            analytics["avgActualVsRecommendedVariance"],
        )

        # build current and suggested rule
        # for stage_1 — just report, no suggestion
        # for stage_2/3 — suggest spread adjustment
        current_spread  = None
        suggested_spread = None

        scenarios = item_rule.get("scenarios", {})
        if scenarios:
            # pick most relevant scenario for this segment
            segment_parts  = [p.strip() for p in segment.split("+")]
            event_type     = segment_parts[0] if segment_parts else ""
            scenario_key   = next(iter(scenarios), None)
            if scenario_key:
                current_spread = scenarios[scenario_key].get("spread")

                # suggest adjustment based on analytics
                if current_spread and learning_stage in ("stage_2", "stage_3"):
                    adjustment = 1.0
                    if analytics["shortageFrequencyPct"] >= 20:
                        adjustment = 0.9   # reduce servesPerTray → more trays
                    elif analytics["avgLeftoverPct"] >= 30:
                        adjustment = 1.1   # increase servesPerTray → fewer trays

                    suggested_spread = {
                        "S": round(current_spread["S"] * adjustment, 2),
                        "M": round(current_spread["M"] * adjustment, 2),
                        "L": round(current_spread["L"] * adjustment, 2),
                    }

        # confidence based on orders and stage
        confidence = min(analytics["totalOrders"] / 100, 1.0)

        recommendation_id = f"REC-{uuid.uuid4().hex[:12].upper()}"

        doc = {
            "recommendationId":    recommendation_id,
            "restaurantId":        RESTAURANT_ID,
            "ruleVersionId":       rule_version_id,
            "cycleId":             cycle_id,
            "cycleStartDate":      cycle_start,
            "cycleEndDate":        cycle_end,
            "triggerType":         "auto_date_and_count",
            "ordersAnalysed":      orders_analysed,
            "itemCode":            item_code,
            "menuName":            menu_name,
            "segment":             segment,
            "learningStage":       learning_stage,
            "currentRule": {
                "ruleField":     "spread",
                "currentValue":  None,
                "currentSpread": current_spread,
            },
            "suggestedRule": {
                "ruleField":       "spread",
                "suggestedValue":  None,
                "suggestedSpread": suggested_spread,
            },
            "confidence":     round(confidence, 2),
            "basedOnOrders":  analytics["totalOrders"],
            "reason":         reason,
            "analytics": {
                "avgLeftoverPct":                 analytics["avgLeftoverPct"],
                "shortageFrequencyPct":           analytics["shortageFrequencyPct"],
                "avgActualVsRecommendedVariance": analytics["avgActualVsRecommendedVariance"],
                "estimatedImpact":                analytics["estimatedImpact"],
            },
            "status":               RecommendationStatus.PENDING.value,
            "approvedBy":           None,
            "approvedAt":           None,
            "newRuleVersionCreated": None,
            "generatedAt":          now,
            "createdAt":            now,
        }

        await db[COLLECTION].insert_one(doc)
        recommendations_count += 1

    return recommendations_count


# ── Approve / Reject ──────────────────────────────────────────────────────────

async def approve_recommendation(
    recommendation_id: str,
    approved_by: str,
) -> Optional[dict]:
    db  = get_db()
    now = datetime.now(timezone.utc)

    rec = await db[COLLECTION].find_one({
        "restaurantId":    RESTAURANT_ID,
        "recommendationId": recommendation_id,
        "status":          RecommendationStatus.PENDING.value,
    })
    if not rec:
        return None

    # create new rule version
    from app.schemas.rule_versions import RuleVersionCreate
    from app.services.rule_versions_service import create_version

    version_data = RuleVersionCreate(
        versionLabel=f"Learning approval — {rec['itemCode']} — {now.strftime('%b %Y')}",
        source=VersionSource.LEARNING_APPROVAL,
        notes=f"Learning engine recommendation approved for {rec['itemCode']} segment: {rec['segment']}",
        publishedBy=approved_by,
        totalItemsImported=0,
    )
    version_doc    = await create_version(version_data)
    new_version_id = version_doc["versionId"]

    # update menu_item_rules with suggested spread
    suggested_spread = rec.get("suggestedRule", {}).get("suggestedSpread")
    if suggested_spread:
        item_rule = await db["menu_item_rules"].find_one({
            "restaurantId": RESTAURANT_ID,
            "itemCode":     rec["itemCode"],
            "isActive":     True,
        })
        if item_rule:
            scenarios = item_rule.get("scenarios", {})
            if scenarios:
                scenario_key = next(iter(scenarios), None)
                if scenario_key:
                    scenarios[scenario_key]["spread"] = suggested_spread
                    await db["menu_item_rules"].update_one(
                        {"restaurantId": RESTAURANT_ID, "itemCode": rec["itemCode"], "isActive": True},
                        {"$set": {
                            "scenarios":     scenarios,
                            "ruleVersionId": new_version_id,
                            "updatedAt":     now,
                        }}
                    )

    result = await db[COLLECTION].find_one_and_update(
        {"recommendationId": recommendation_id},
        {"$set": {
            "status":               RecommendationStatus.APPROVED.value,
            "approvedBy":           approved_by,
            "approvedAt":           now,
            "newRuleVersionCreated": new_version_id,
        }},
        return_document=True
    )
    return _serialize(result)


async def reject_recommendation(
    recommendation_id: str,
    rejected_by: str,
) -> Optional[dict]:
    db  = get_db()
    now = datetime.now(timezone.utc)

    result = await db[COLLECTION].find_one_and_update(
        {
            "restaurantId":     RESTAURANT_ID,
            "recommendationId": recommendation_id,
            "status":           RecommendationStatus.PENDING.value,
        },
        {"$set": {
            "status":     RecommendationStatus.REJECTED.value,
            "approvedBy": rejected_by,
            "approvedAt": now,
        }},
        return_document=True
    )
    return _serialize(result) if result else None


# ── GET functions ─────────────────────────────────────────────────────────────

async def get_recommendation_by_id(recommendation_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId":     RESTAURANT_ID,
        "recommendationId": recommendation_id,
    })
    return _serialize(doc) if doc else None


async def get_all_recommendations(
    status: Optional[str] = None,
    cycle_id: Optional[str] = None,
    item_code: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if status:
        query["status"] = status
    if cycle_id:
        query["cycleId"] = cycle_id
    if item_code:
        query["itemCode"] = item_code

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("generatedAt", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def create_indexes():
    db = get_db()

    # { restaurantId, status } — owner dashboard shows pending
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("status", 1)],
        name="idx_restaurantId_status"
    )
    # { cycleId } — groups recommendations from same cycle
    await db[COLLECTION].create_index(
        [("cycleId", 1)],
        name="idx_cycleId"
    )
    # { restaurantId, generatedAt: -1 } — history listing
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("generatedAt", -1)],
        name="idx_restaurantId_generatedAt_desc"
    )
    # { itemCode, segment } — duplicate check
    await db[COLLECTION].create_index(
        [("itemCode", 1), ("segment", 1)],
        name="idx_itemCode_segment"
    )
    print(f"Indexes created for {COLLECTION}")