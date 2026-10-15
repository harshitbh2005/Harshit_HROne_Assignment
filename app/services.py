"""
Business logic for attendance operations.

Keeping the logic out of the routers makes it easier to test and
easier to talk through in the live review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException, status

from app.database import attendance_col, employees_col

IST = ZoneInfo("Asia/Kolkata")

# Anything more than 15 minutes after shift start is considered late.
LATE_THRESHOLD_MINUTES = 15

# Minimum working hours in a day to count as "present" (not half-day)
MIN_HOURS_FULL_DAY = 4.0


def _now_ist() -> datetime:
    """Return current time as timezone-aware datetime in IST."""
    return datetime.now(IST)


def _to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        # Assume UTC when no tzinfo is given (common for stored datetimes)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


async def _get_employee(employee_id: str) -> dict:
    emp = await employees_col().find_one({"employee_id": employee_id})
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{employee_id}' not found. Add them first via POST /employees."
        )
    return emp


async def _get_last_record_today(employee_id: str) -> Optional[dict]:
    """Return today's attendance document for this employee, if any."""
    today = _now_ist().date().isoformat()
    return await attendance_col().find_one(
        {"employee_id": employee_id, "date": today}
    )


async def punch_in(employee_id: str, timestamp: Optional[datetime], notes: Optional[str]) -> dict:
    """
    Record a punch-in.

    Business rules:
    - Employee must exist.
    - Can't punch in twice on the same day without punching out first.
    - If punch_in time is more than LATE_THRESHOLD_MINUTES after shift start, mark as LATE.
    """
    emp = await _get_employee(employee_id)

    punch_time = timestamp if timestamp else _now_ist()
    if punch_time.tzinfo is None:
        punch_time = punch_time.replace(tzinfo=IST)
    punch_time_ist = _to_ist(punch_time)
    today = punch_time_ist.date().isoformat()

    existing = await attendance_col().find_one({"employee_id": employee_id, "date": today})
    if existing and existing.get("punch_in") and not existing.get("punch_out"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already punched in today. Please punch out first."
        )
    if existing and existing.get("punch_in") and existing.get("punch_out"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already completed attendance for today (both punch-in and punch-out recorded)."
        )

    # Figure out late status
    shift_start_str = emp.get("shift_start", "09:30")
    sh, sm = map(int, shift_start_str.split(":"))
    shift_start_dt = punch_time_ist.replace(hour=sh, minute=sm, second=0, microsecond=0)
    diff_minutes = (punch_time_ist - shift_start_dt).total_seconds() / 60
    is_late = diff_minutes > LATE_THRESHOLD_MINUTES

    doc = {
        "employee_id": employee_id,
        "date": today,
        "punch_in": punch_time_ist,
        "punch_out": None,
        "working_minutes": None,
        "status": "LATE" if is_late else "PRESENT",
        "is_manual_corrected": False,
        "audit_trail": [],
        "notes_in": notes,
        "notes_out": None,
    }

    result = await attendance_col().insert_one(doc)
    return {
        "record_id": str(result.inserted_id),
        "employee_id": employee_id,
        "punch_type": "IN",
        "timestamp": punch_time_ist,
        "status": "ok",
    }


async def punch_out(employee_id: str, timestamp: Optional[datetime], notes: Optional[str]) -> dict:
    """
    Record a punch-out.

    Business rules:
    - Must have a punch-in for today first.
    - Can't punch out twice.
    - Working minutes are calculated and stored.
    - If working < MIN_HOURS_FULL_DAY we downgrade status to HALF_DAY.
    """
    punch_time = timestamp if timestamp else _now_ist()
    if punch_time.tzinfo is None:
        punch_time = punch_time.replace(tzinfo=IST)
    punch_time_ist = _to_ist(punch_time)
    today = punch_time_ist.date().isoformat()

    record = await attendance_col().find_one({"employee_id": employee_id, "date": today})

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No punch-in found for today. Please punch in first."
        )
    if record.get("punch_out"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already punched out for today."
        )

    punch_in_time = record["punch_in"]
    if punch_in_time.tzinfo is None:
        punch_in_time = punch_in_time.replace(tzinfo=timezone.utc)
    punch_in_ist = _to_ist(punch_in_time)

    if punch_time_ist < punch_in_ist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Punch-out time cannot be before punch-in time."
        )

    working_minutes = int((punch_time_ist - punch_in_ist).total_seconds() / 60)
    current_status = record.get("status", "PRESENT")
    if working_minutes < MIN_HOURS_FULL_DAY * 60:
        # Override status to HALF_DAY if they didn't work enough hours,
        # but preserve LATE if it was already set
        if current_status not in ("LATE",):
            current_status = "HALF_DAY"

    await attendance_col().update_one(
        {"_id": record["_id"]},
        {
            "$set": {
                "punch_out": punch_time_ist,
                "working_minutes": working_minutes,
                "status": current_status,
                "notes_out": notes,
            }
        }
    )

    return {
        "record_id": str(record["_id"]),
        "employee_id": employee_id,
        "punch_type": "OUT",
        "timestamp": punch_time_ist,
        "status": "ok",
    }


async def manual_correction(
    record_id: str,
    corrected_by: str,
    reason: str,
    new_punch_in: Optional[datetime],
    new_punch_out: Optional[datetime],
) -> dict:
    """
    Allow an admin to fix punch times.
    Every change is appended to the audit_trail array in the document.
    """
    try:
        oid = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid record ID format.")

    record = await attendance_col().find_one({"_id": oid})
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found.")

    audit_entry = {
        "corrected_by": corrected_by,
        "corrected_at": _now_ist(),
        "reason": reason,
        "old_punch_in":  record.get("punch_in"),
        "old_punch_out": record.get("punch_out"),
        "new_punch_in":  new_punch_in,
        "new_punch_out": new_punch_out,
    }

    update_fields: dict = {"is_manual_corrected": True}
    if new_punch_in:
        pi = _to_ist(new_punch_in) if new_punch_in.tzinfo else new_punch_in.replace(tzinfo=IST)
        update_fields["punch_in"] = pi
    if new_punch_out:
        po = _to_ist(new_punch_out) if new_punch_out.tzinfo else new_punch_out.replace(tzinfo=IST)
        update_fields["punch_out"] = po

    # Recalculate working minutes if we have both times after correction
    final_in  = update_fields.get("punch_in",  record.get("punch_in"))
    final_out = update_fields.get("punch_out", record.get("punch_out"))
    if final_in and final_out:
        if final_in.tzinfo is None:
            final_in = final_in.replace(tzinfo=timezone.utc)
        if final_out.tzinfo is None:
            final_out = final_out.replace(tzinfo=timezone.utc)
        update_fields["working_minutes"] = int((final_out - final_in).total_seconds() / 60)

    await attendance_col().update_one(
        {"_id": oid},
        {
            "$set": update_fields,
            "$push": {"audit_trail": audit_entry},
        }
    )

    return {"status": "corrected", "record_id": record_id}
