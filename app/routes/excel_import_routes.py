import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from app.core.constants import RESTAURANT_ID
from app.schemas.excel_import_jobs import ExcelImportJobCreate
from app.services import excel_import_jobs_service as job_service
from app.services.import_service import run_import

router = APIRouter(prefix="/import", tags=["Excel Import"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/", response_model=dict, status_code=201)
async def import_excel(
    uploaded_by: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload main Excel file and trigger full import pipeline.
    Use POST /import/combo separately to upload combo spread file.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files accepted")

    file_path = os.path.join(UPLOAD_DIR, f"{RESTAURANT_ID}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_size = os.path.getsize(file_path)

    job_data = ExcelImportJobCreate(
        uploadedBy=uploaded_by,
        fileName=file.filename,
        fileSize=file_size,
        filePath=file_path
    )
    job_doc = await job_service.create_job(job_data)
    import_job_id = job_doc["importJobId"]

    result = await run_import(
        import_job_id=import_job_id,
        file_path=file_path,
        uploaded_by=uploaded_by,
        combo_file_path=None
    )
    return {"success": result["success"], "importJobId": import_job_id, "data": result}


@router.delete("/restaurant", response_model=dict, summary="Delete all imported data")
async def delete_by_restaurant():
    """
    Delete ALL import-related data for a restaurant.
    Removes import job history and menu rule records.
    """
    deleted = await job_service.delete_by_restaurant()
    if not deleted:
        raise HTTPException(status_code=404, detail="No records found for this restaurant")
    return {
        "success": True,
        "message": "Records deleted successfully",
        "deletedCount": deleted
    }


@router.get("/", response_model=dict)
async def list_import_jobs():
    """List all import jobs."""
    jobs = await job_service.get_all_jobs()
    return {"success": True, "count": len(jobs), "data": jobs}


@router.get("/{import_job_id}", response_model=dict)
async def get_import_job(import_job_id: str):
    """Get single import job detail."""
    job = await job_service.get_job(import_job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return {"success": True, "data": job}
