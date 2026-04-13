"""ROADAI Async Jobs API — for background video processing."""
import json
from fastapi import APIRouter, HTTPException
from backend.db.database import get_db, docs_to_list, doc_to_dict

router = APIRouter()

@router.get("/")
async def list_jobs(limit: int=20):
    db = await get_db()
    cursor = db.jobs.find().sort("created_at", -1).limit(limit)
    return {"jobs": docs_to_list(await cursor.to_list(length=limit))}

@router.get("/{job_id}")
async def get_job(job_id: str):
    db = await get_db()
    doc = await db.jobs.find_one({"id": job_id})
    if not doc: raise HTTPException(404, "Job not found")
    return doc_to_dict(doc)

@router.delete("/{job_id}")
async def delete_job(job_id: str):
    db = await get_db()
    res = await db.jobs.delete_one({"id": job_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Job not found")
    return {"deleted": job_id}
