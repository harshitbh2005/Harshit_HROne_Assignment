"""
analytics.py

All the reporting endpoints. The important thing here is that all the heavy
lifting is done inside MongoDB using aggregation pipelines - not in Python.

Fetching thousands of records into Python just to sum them up is slow and
wasteful. MongoDB's aggregation framework handles this much better.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.database import attendance_col, employees_col

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _month_date_range(year: int, month: int) -> tuple[str, str]:
    """returns first and last date of a given month as ISO strings"""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year}-{month:02d}-01"
    end   = f"{year}-{month:02d}-{last_day:02d}"
    return start, end


# -----------------------------------------------------------------------
# 1. Total working hours for an employee in a month
# -----------------------------------------------------------------------

@router.get(
    "/hours/{employee_id}",
    summary="Monthly working hours summary for an employee",
)
async def working_hours_summary(
    employee_id: str,
    year:  int = Query(..., description="e.g. 2026"),
    month: int = Query(..., ge=1, le=12),
):
    start, end = _month_date_range(year, month)

    # filter to this employee + month, then group and sum working_minutes
    # $round to 2 decimal places so we don't get 176.666666... hours
    pipeline = [
        {
            "$match": {
                "employee_id": employee_id,
                "date": {"$gte": start, "$lte": end},
                "working_minutes": {"$ne": None},  # skip records with no punch-out yet
            }
        },
        {
            "$group": {
                "_id": "$employee_id",
                "total_minutes": {"$sum": "$working_minutes"},
                "days_present":  {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "employee_id": {"$literal": employee_id},
                "total_working_hours": {
                    "$round": [{"$divide": ["$total_minutes", 60]}, 2]
                },
                "days_present": 1,
                "average_hours_per_day": {
                    "$round": [
                        {"$divide": [{"$divide": ["$total_minutes", 60]}, "$days_present"]},
                        2,
                    ]
                },
            }
        },
    ]

    results = await attendance_col().aggregate(pipeline).to_list(length=1)

    # return zeros if employee has no records for that month
    if not results:
        return {
            "employee_id": employee_id,
            "total_working_hours": 0,
            "days_present": 0,
            "average_hours_per_day": 0,
            "period_start": start,
            "period_end": end,
        }

    data = results[0]
    data["period_start"] = start
    data["period_end"]   = end
    return data


# -----------------------------------------------------------------------
# 2. Late arrivals in a date range
# -----------------------------------------------------------------------

@router.get(
    "/late-arrivals",
    summary="Who came late, and when",
)
async def late_arrivals(
    start_date: str = Query(..., description="e.g. 2026-10-01"),
    end_date:   str = Query(..., description="e.g. 2026-10-15"),
    employee_id: Optional[str] = Query(None, description="filter to one employee"),
):
    match_stage: dict = {
        "date":   {"$gte": start_date, "$lte": end_date},
        "status": "LATE",
    }
    if employee_id:
        match_stage["employee_id"] = employee_id

    pipeline = [
        {"$match": match_stage},
        {
            "$project": {
                "_id": 0,
                "employee_id": 1,
                "date": 1,
                "punch_in": 1,
                "status": 1,
            }
        },
        {"$sort": {"date": 1, "employee_id": 1}},
    ]

    docs = await attendance_col().aggregate(pipeline).to_list(length=500)
    for d in docs:
        if hasattr(d.get("punch_in"), "isoformat"):
            d["punch_in"] = d["punch_in"].isoformat()
    return {"late_arrivals": docs, "count": len(docs)}


# -----------------------------------------------------------------------
# 3. Who was absent on a specific date
# -----------------------------------------------------------------------

@router.get(
    "/absent/{date}",
    summary="List employees who didn't show up on a given date",
)
async def absent_employees(date: str):
    # get all registered employees
    all_emps_cursor = employees_col().find({}, {"employee_id": 1, "name": 1, "_id": 0})
    all_emps = await all_emps_cursor.to_list(length=1000)
    all_ids = {e["employee_id"] for e in all_emps}

    # get everyone who has any attendance record on that date
    pipeline = [
        {"$match": {"date": date}},
        {"$group": {"_id": "$employee_id"}},
    ]
    present_raw = await attendance_col().aggregate(pipeline).to_list(length=1000)
    present_ids = {r["_id"] for r in present_raw}

    # whoever isn't in present_ids was absent
    absent_ids = all_ids - present_ids

    emp_map = {e["employee_id"]: e.get("name", "") for e in all_emps}
    absent = [
        {"employee_id": eid, "name": emp_map.get(eid, "")}
        for eid in sorted(absent_ids)
    ]

    return {"date": date, "absent_employees": absent, "count": len(absent)}


# -----------------------------------------------------------------------
# 4. Department-wise attendance summary
# -----------------------------------------------------------------------

@router.get(
    "/department-summary",
    summary="Attendance stats grouped by department for a month",
)
async def department_summary(
    year:  int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    start, end = _month_date_range(year, month)

    # $lookup is basically a JOIN - pulling in department info from employees collection
    # this is more efficient than doing it in Python with two separate queries
    pipeline = [
        {
            "$match": {
                "date": {"$gte": start, "$lte": end},
                "working_minutes": {"$ne": None},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "employee_id",
                "as": "emp_info",
            }
        },
        {"$unwind": {"path": "$emp_info", "preserveNullAndEmpty": False}},
        {
            "$group": {
                "_id": "$emp_info.department",
                "total_employees": {"$addToSet": "$employee_id"},  # addToSet = unique count
                "total_days_present": {"$sum": 1},
                "total_minutes": {"$sum": "$working_minutes"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "total_employees": {"$size": "$total_employees"},
                "days_present": "$total_days_present",
                "average_hours": {
                    "$round": [
                        {"$divide": [{"$divide": ["$total_minutes", 60]}, "$total_days_present"]},
                        2,
                    ]
                },
            }
        },
        {"$sort": {"department": 1}},
    ]

    results = await attendance_col().aggregate(pipeline).to_list(length=100)
    return {
        "period_start": start,
        "period_end":   end,
        "departments":  results,
    }


# -----------------------------------------------------------------------
# 5. Day-by-day breakdown for one employee in a month
# -----------------------------------------------------------------------

@router.get(
    "/employee-report/{employee_id}",
    summary="Full month breakdown - each day with punch times and status",
)
async def employee_monthly_report(
    employee_id: str,
    year:  int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    start, end = _month_date_range(year, month)

    pipeline = [
        {
            "$match": {
                "employee_id": employee_id,
                "date": {"$gte": start, "$lte": end},
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "punch_in": 1,
                "punch_out": 1,
                "working_minutes": 1,
                "status": 1,
                "is_manual_corrected": 1,
            }
        },
        {"$sort": {"date": 1}},
    ]

    docs = await attendance_col().aggregate(pipeline).to_list(length=100)
    for d in docs:
        for k in ("punch_in", "punch_out"):
            if hasattr(d.get(k), "isoformat"):
                d[k] = d[k].isoformat()

    return {
        "employee_id": employee_id,
        "period_start": start,
        "period_end":   end,
        "records": docs,
    }
