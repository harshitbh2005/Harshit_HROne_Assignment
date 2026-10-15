"""
attendance.py - router for all punch-in/out and correction stuff

Keeping the routes thin - actual logic is in services.py.
These just validate the request and call the right function.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Path, Query, status

from app.database import attendance_col, employees_col
from app.models import CorrectionRequest, EmployeeCreate, PunchRequest
from app.services import manual_correction, punch_in, punch_out

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# --- employee registration ---
# keeping this here instead of a separate employees router to keep things simple

@router.post(
    "/employees",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new employee",
)
async def create_employee(body: EmployeeCreate):
    existing = await employees_col().find_one({"employee_id": body.employee_id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee '{body.employee_id}' already exists."
        )
    await employees_col().insert_one(body.model_dump())
    return {"status": "created", "employee_id": body.employee_id}


@router.get("/employees", summary="List all employees")
async def list_employees():
    cursor = employees_col().find({}, {"_id": 0})
    return {"employees": await cursor.to_list(length=500)}


# --- punch in ---

@router.post(
    "/punch-in",
    status_code=status.HTTP_201_CREATED,
    summary="Record employee punch-in",
)
async def record_punch_in(body: PunchRequest):
    result = await punch_in(body.employee_id, body.timestamp, body.notes)
    return result


# --- punch out ---

@router.post(
    "/punch-out",
    status_code=status.HTTP_200_OK,
    summary="Record employee punch-out",
)
async def record_punch_out(body: PunchRequest):
    result = await punch_out(body.employee_id, body.timestamp, body.notes)
    return result


# --- manual correction ---

@router.patch(
    "/records/{record_id}/correct",
    summary="Manually correct an attendance record (admin only)",
)
async def correct_record(
    record_id: str = Path(..., description="MongoDB ObjectId of the attendance record"),
    body: CorrectionRequest = ...,
):
    result = await manual_correction(
        record_id=record_id,
        corrected_by=body.corrected_by,
        reason=body.reason,
        new_punch_in=body.new_punch_in,
        new_punch_out=body.new_punch_out,
    )
    return result


# --- fetching records ---

@router.get(
    "/records/{record_id}",
    summary="Get a single attendance record by ID",
)
async def get_record(record_id: str = Path(...)):
    try:
        oid = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid record ID.")

    doc = await attendance_col().find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Record not found.")

    doc["_id"] = str(doc["_id"])
    # convert datetimes to strings so JSON doesn't complain
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    if isinstance(doc.get("audit_trail"), list):
        for entry in doc["audit_trail"]:
            for ek, ev in entry.items():
                if isinstance(ev, datetime):
                    entry[ek] = ev.isoformat()
    return doc


@router.get(
    "/records",
    summary="List records - filter by employee_id or date",
)
async def list_records(
    employee_id: Optional[str] = Query(None),
    date: Optional[str]        = Query(None, description="e.g. 2026-10-15"),
    skip: int                  = Query(0, ge=0),
    limit: int                 = Query(50, ge=1, le=500),
):
    query: dict = {}
    if employee_id:
        query["employee_id"] = employee_id
    if date:
        query["date"] = date

    cursor = attendance_col().find(query).skip(skip).limit(limit).sort("punch_in", -1)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
        for k, v in doc.items():
            if isinstance(v, datetime):
                doc[k] = v.isoformat()
    return {"records": docs, "count": len(docs)}
