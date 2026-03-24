from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID, Decision, VersionSource
from app.schemas.override_approvals import OverrideApprovalCreate

COLLECTION = "override_approvals"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── What happens on approval ──────────────────────────────────────────────────

async def _handle_calculation_approval(
    override_request: dict,
    approval_id: str,
) -> None:
    """
    approved + overrideType: calculation
    → update calculation_results: overrideApplied: true, overrideId populated
    """
    db         = get_db()
    result_id  = override_request["impactedOn"].get("resultId")
    new_value  = override_request["newValue"]

    if not result_id:
        return

    update_fields = {
        "overrideApplied": True,
        "overrideId":      approval_id,
        "status":          "overridden",
    }

    # apply new tray values or piece count to the specific item
    item_code = override_request["impactedOn"]["itemCode"]

    result_doc = await db["calculation_results"].find_one({"resultId": result_id})
    if not result_doc:
        return

    item_results = result_doc.get("itemResults", [])
    for item in item_results:
        if item.get("itemCode") == item_code:
            if "totalPieces" in new_value:
                item["totalPieces"] = new_value["totalPieces"]
            else:
                item["trayResult"] = new_value
            item["overrideApplied"] = True
            item["overrideId"]      = approval_id
            break

    update_fields["itemResults"] = item_results

    await db["calculation_results"].update_one(
        {"resultId": result_id},
        {"$set": update_fields}
    )


async def _handle_rule_approval(
    override_request: dict,
    approved_by: str,
) -> str:
    """
    approved + overrideType: rule
    → update menu_item_rules + create new rule_version
    → returns new versionId
    """
    db        = get_db()
    now       = datetime.now(timezone.utc)
    item_code = override_request["impactedOn"]["itemCode"]
    rule_field = override_request["impactedOn"].get("ruleField")
    new_value  = override_request["newValue"]

    # create new rule version
    from app.schemas.rule_versions import RuleVersionCreate
    from app.services.rule_versions_service import create_version

    version_data = RuleVersionCreate(
        versionLabel=f"Override approval — {item_code} — {now.strftime('%b %Y')}",
        source=VersionSource.OVERRIDE_APPROVAL,
        notes=f"Rule override approved for {item_code} field: {rule_field}",
        publishedBy=approved_by,
        totalItemsImported=0,
    )
    version_doc = await create_version(version_data)
    new_version_id = version_doc["versionId"]

    # update menu_item_rules
    update_fields = {
        "updatedAt":    now,
        "ruleVersionId": new_version_id,
        "source":       "override_approval",
    }
    if rule_field:
        update_fields[rule_field] = new_value.get(rule_field) or list(new_value.values())[0]

    await db["menu_item_rules"].update_one(
        {"restaurantId": RESTAURANT_ID, "itemCode": item_code, "isActive": True},
        {"$set": update_fields}
    )

    return new_version_id


# ── Main service functions ────────────────────────────────────────────────────

async def create_override_approval(
    data: OverrideApprovalCreate,
    approved_by: str,
    approved_by_role: str,
) -> dict:
    db  = get_db()
    now = datetime.now(timezone.utc)

    # fetch the override_request
    override_request = await db["override_requests"].find_one({
        "restaurantId":      RESTAURANT_ID,
        "overrideRequestId": data.overrideRequestId,
        "status":            "pending"
    })
    if not override_request:
        raise ValueError(
            f"Override request '{data.overrideRequestId}' not found or already processed."
        )

    # one approval per request — cannot approve same request twice
    existing_approval = await db[COLLECTION].find_one({
        "overrideRequestId": data.overrideRequestId
    })
    if existing_approval:
        raise ValueError(
            f"Override request '{data.overrideRequestId}' has already been processed."
        )

    approval_id        = f"APR-{uuid.uuid4().hex[:12].upper()}"
    rule_version_created = None
    is_active          = False
    override_type      = override_request.get("overrideType")

    # ── Handle approval actions ───────────────────────────────────────────────
    if data.decision == Decision.APPROVED:
        is_active = True

        if override_type == "calculation":
            await _handle_calculation_approval(override_request, approval_id)

        elif override_type == "rule":
            rule_version_created = await _handle_rule_approval(override_request, approved_by)

        # update override_request status to approved
        await db["override_requests"].update_one(
            {"overrideRequestId": data.overrideRequestId},
            {"$set": {"status": "approved", "updatedAt": now}}
        )

    elif data.decision == Decision.REJECTED:
        # audit log only — nothing changes in engine
        await db["override_requests"].update_one(
            {"overrideRequestId": data.overrideRequestId},
            {"$set": {"status": "rejected", "updatedAt": now}}
        )

    # ── Build approval document ───────────────────────────────────────────────
    doc = {
        "approvalId":          approval_id,
        "overrideRequestId":   data.overrideRequestId,
        "restaurantId":        RESTAURANT_ID,
        "approvedBy":          approved_by,
        "approvedByRole":      approved_by_role,
        "decision":            data.decision.value,
        "decisionNotes":       data.decisionNotes,
        "decidedAt":           now,
        "effectiveFrom":       override_request.get("effectiveFrom"),
        "effectiveTo":         override_request.get("effectiveTo"),
        "impactedOn":          override_request.get("impactedOn"),
        "oldValue":            override_request.get("oldValue"),
        "newValue":            override_request.get("newValue"),
        "ruleVersionCreated":  rule_version_created,
        "isActive":            is_active,
        "createdAt":           now,
    }

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def get_approval_by_id(approval_id: str) -> Optional[dict]:
    db  = get_db()
    doc = await db[COLLECTION].find_one({
        "restaurantId": RESTAURANT_ID,
        "approvalId":   approval_id
    })
    return _serialize(doc) if doc else None


async def get_all_approvals(
    decision: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20
) -> dict:
    db    = get_db()
    query: dict = {"restaurantId": RESTAURANT_ID}

    if decision:
        query["decision"] = decision
    if is_active is not None:
        query["isActive"] = is_active

    skip  = (page - 1) * page_size
    total = await db[COLLECTION].count_documents(query)

    cursor = db[COLLECTION].find(query).sort("decidedAt", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))

    return {"total": total, "page": page, "page_size": page_size, "results": results}


async def expire_temporary_overrides() -> int:
    """
    Background job — runs daily.
    Checks isActive: true and effectiveTo < now → sets isActive: false.
    Critical for temporary override expiry.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    result = await db[COLLECTION].update_many(
        {
            "restaurantId": RESTAURANT_ID,
            "isActive":     True,
            "effectiveTo":  {"$lt": now, "$ne": None}
        },
        {"$set": {"isActive": False}}
    )

    print(f"Expired {result.modified_count} temporary overrides")
    return result.modified_count


async def create_indexes():
    db = get_db()

    # { restaurantId, isActive, effectiveFrom, effectiveTo } — override resolver
    await db[COLLECTION].create_index(
        [
            ("restaurantId", 1),
            ("isActive", 1),
            ("effectiveFrom", 1),
            ("effectiveTo", 1),
        ],
        name="idx_override_resolver"
    )
    # { overrideRequestId } unique — link to override_request
    await db[COLLECTION].create_index(
        [("overrideRequestId", 1)],
        unique=True,
        name="idx_overrideRequestId_unique"
    )
    # { approvalId } — referenced by calculation_results
    await db[COLLECTION].create_index(
        [("approvalId", 1)],
        name="idx_approvalId"
    )
    # { restaurantId, decidedAt: -1 } — audit history
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("decidedAt", -1)],
        name="idx_restaurantId_decidedAt_desc"
    )
    print(f"Indexes created for {COLLECTION}")
