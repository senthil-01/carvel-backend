from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_db
from app.core.constants import ImportStatus, RESTAURANT_ID
from app.schemas.excel_import_jobs import (
    ExcelImportJobCreate, ValidationResult, ImportResult
)

COLLECTION = "excel_import_jobs"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def create_job(data: ExcelImportJobCreate) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    import_job_id = f"job_{RESTAURANT_ID}_{int(now.timestamp())}"
    doc = data.model_dump()
    doc["restaurantId"] = RESTAURANT_ID
    doc["importJobId"] = import_job_id
    doc["status"] = ImportStatus.UPLOADING
    doc["sheets"] = []
    doc["validationResult"] = None
    doc["importResult"] = None
    doc["completedAt"] = None
    doc["createdAt"] = now
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def update_job_status(
    import_job_id: str,
    status: ImportStatus,
    sheets: Optional[list] = None,
    validation_result: Optional[dict] = None,
    import_result: Optional[dict] = None
):
    db = get_db()
    update = {"status": status}
    if sheets is not None:
        update["sheets"] = sheets
    if validation_result is not None:
        update["validationResult"] = validation_result
    if import_result is not None:
        update["importResult"] = import_result
        update["completedAt"] = datetime.now(timezone.utc)
    await db[COLLECTION].update_one(
        {"importJobId": import_job_id},
        {"$set": update}
    )


async def get_job(import_job_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db[COLLECTION].find_one({"importJobId": import_job_id})
    return _serialize(doc) if doc else None


async def get_all_jobs() -> list:
    db = get_db()
    cursor = db[COLLECTION].find(
        {"restaurantId": RESTAURANT_ID},
        sort=[("createdAt", -1)]
    )
    results = []
    async for doc in cursor:
        results.append(_serialize(doc))
    return results


async def create_indexes():
    db = get_db()
    await db[COLLECTION].create_index(
        [("restaurantId", 1), ("createdAt", -1)]
    )
    await db[COLLECTION].create_index([("importJobId", 1)], unique=True)
    await db[COLLECTION].create_index([("status", 1)])
    print(f"Indexes created for {COLLECTION}")


async def delete_by_restaurant() -> int:
    """
    Deletes all records related to a restaurant.
    Returns total deleted count.
    """
    db = get_db()

    # Delete from import jobs collection
    result_jobs = await db.excel_import_jobs.delete_many({
        "restaurantId": RESTAURANT_ID
    })

    # Delete from menu rules collection
    result_rules = await db.menu_item_rules.delete_many({
        "restaurantId": RESTAURANT_ID
    })

    total_deleted = result_jobs.deleted_count + result_rules.deleted_count

    print(f"Deleted Jobs: {result_jobs.deleted_count}")
    print(f"Deleted Rules: {result_rules.deleted_count}")

    return total_deleted