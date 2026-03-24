import os
import math
from datetime import datetime, timezone
from typing import Optional
from app.core.database import get_db
from app.core.constants import ImportStatus, VersionSource, RESTAURANT_ID
from app.utils.excel_parser import parse_excel_file
from app.services import excel_import_jobs_service as job_service
from app.services import rule_versions_service as version_service
from app.services import menu_item_rules_service as item_service


VALID_CATEGORIES = ["Appetizer", "Entree", "Rice", "Bread", "Dessert"]
VALID_VEG = ["Veg", "Non Veg", "Non-Veg"]
VALID_ROUNDING = ["full_tray", "half_tray", "next_integer", "min_one"]
VALID_SIZES = ["Small", "Medium", "Large", "Regular"]


def _validate_item(item_data: dict, row: int, sheet: str) -> list:
    """Validate a single item row. Returns list of errors."""
    errors = []

    if not item_data.get("menuName"):
        errors.append({"sheet": sheet, "row": row, "itemName": None, "field": "menuName", "issue": "menuName is required"})

    if not item_data.get("vegNonVeg"):
        errors.append({"sheet": sheet, "row": row, "itemName": item_data.get("menuName"), "field": "vegNonVeg", "issue": "vegNonVeg is required"})

    if item_data.get("adjustmentPct") is None:
        errors.append({"sheet": sheet, "row": row, "itemName": item_data.get("menuName"), "field": "adjustmentPct", "issue": "adjustmentPct is required"})

    if item_data.get("sellByCount") and not item_data.get("size"):
        errors.append({"sheet": sheet, "row": row, "itemName": item_data.get("menuName"), "field": "size", "issue": "size is required for sell-by-count items"})

    if not item_data.get("sellByCount") and not item_data.get("scenarios"):
        errors.append({"sheet": sheet, "row": row, "itemName": item_data.get("menuName"), "field": "scenarios", "issue": "scenarios are required for sell-by-tray items"})

    mult = item_data.get("adjustmentMultiplier")
    if mult is not None and mult <= 0:
        errors.append({"sheet": sheet, "row": row, "itemName": item_data.get("menuName"), "field": "adjustmentMultiplier", "issue": "adjustmentMultiplier must be positive"})

    return errors


async def run_import(
    import_job_id: str,
    file_path: str,
    uploaded_by: str,
    combo_file_path: Optional[str] = None
) -> dict:
    """
    Main import orchestrator.
    1. Parse Excel
    2. Validate all rows
    3. Create rule version
    4. Save items to menu_item_rules
    5. Save combo spread if provided
    6. Update job status
    """

    # Step 1 — Update job to validating
    await job_service.update_job_status(import_job_id, ImportStatus.VALIDATING)

    # Step 2 — Parse Excel file
    try:
        parsed = parse_excel_file(file_path)
    except Exception as e:
        await job_service.update_job_status(
            import_job_id,
            ImportStatus.FAILED,
            validation_result={
                "passed": False,
                "totalRowsFound": 0,
                "totalRowsValid": 0,
                "totalRowsSkipped": 0,
                "errors": [{"sheet": "file", "row": 0, "field": "file", "issue": str(e)}]
            }
        )
        return {"success": False, "error": str(e)}

    all_items = parsed["items"]
    sheets_found = parsed["sheetsFound"]
    total_found = parsed["totalFound"]

    # Step 3 — Validate all rows
    all_errors = []
    valid_items = []
    skipped_items = []

    for entry in all_items:
        item_data = entry["data"]
        row = entry["row"]
        sheet = item_data.pop("sheet", "unknown")
        errors = _validate_item(item_data, row, sheet)
        if errors:
            all_errors.extend(errors)
            skipped_items.append(entry)
        else:
            valid_items.append(item_data)

    validation_result = {
        "passed": len(all_errors) == 0,
        "totalRowsFound": total_found,
        "totalRowsValid": len(valid_items),
        "totalRowsSkipped": len(skipped_items),
        "errors": all_errors
    }

    # Step 4 — If all failed, mark job as failed
    if len(valid_items) == 0:
        await job_service.update_job_status(
            import_job_id,
            ImportStatus.FAILED,
            sheets=sheets_found,
            validation_result=validation_result
        )
        return {"success": False, "validationResult": validation_result}

    # Step 5 — Create rule version
    from app.schemas.rule_versions import RuleVersionCreate
    version_data = RuleVersionCreate(
        versionLabel=f"Excel import — {datetime.now(timezone.utc).strftime('%b %Y')}",
        source=VersionSource.EXCEL_IMPORT,
        importJobId=import_job_id,
        totalItemsImported=len(valid_items),
        notes=f"Imported {len(valid_items)} items from Excel",
        publishedBy=uploaded_by
    )
    version_doc = await version_service.create_version(version_data)
    version_id = version_doc["versionId"]

    # Step 6 — Deactivate old items and activate new version
    await item_service.deactivate_items_by_version(version_id)
    await version_service.activate_version(version_id)

    # Step 7 — Save all valid items to menu_item_rules
    categories_imported = set()
    db = get_db()
    now = datetime.now(timezone.utc)

    for item_data in valid_items:
        item_data["restaurantId"] = RESTAURANT_ID
        item_data["ruleVersionId"] = version_id
        item_data["importJobId"] = import_job_id
        item_data["isActive"] = True
        item_data["source"] = "excel"
        item_data["createdAt"] = now
        item_data["updatedAt"] = now
        categories_imported.add(item_data.get("category", "Unknown"))
        await db["menu_item_rules"].insert_one(item_data)

   
    # Step 9 — Build import result
    import_result = {
        "totalItemsImported": len(valid_items),
        "totalMultipliersImported": 0,
        "categoriesImported": list(categories_imported),
        "ruleVersionCreated": version_id
    }

    # Step 10 — Update job to completed or partial
    final_status = ImportStatus.COMPLETED if len(all_errors) == 0 else ImportStatus.PARTIAL
    await job_service.update_job_status(
        import_job_id,
        final_status,
        sheets=list(sheets_found),
        validation_result=validation_result,
        import_result=import_result
    )

    return {
        "success": True,
        "status": final_status,
        "importJobId": import_job_id,
        "ruleVersionCreated": version_id,
        "totalItemsImported": len(valid_items),
        "totalSkipped": len(skipped_items),
        "categoriesImported": list(categories_imported),
        "errors": all_errors
    }
