"""
Pydantic models used as request/response bodies throughout the API.

We deliberately keep this flat (no deep inheritance chains) so it's easy
to read and follow during the live review.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

class PyObjectId(str):
    """Make MongoDB ObjectId JSON-serialisable without bson installed separately."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return str(v)


# ---------------------------------------------------------------------------
# Punch / attendance
# ---------------------------------------------------------------------------

class PunchRequest(BaseModel):
    employee_id: str = Field(..., description="Unique employee identifier, e.g. EMP001")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Punch time in ISO-8601. Defaults to server time when absent."
    )
    notes: Optional[str] = Field(None, description="Optional free-text note from the employee")


class PunchResponse(BaseModel):
    status: str
    employee_id: str
    punch_type: Literal["IN", "OUT"]
    timestamp: datetime
    record_id: str


# ---------------------------------------------------------------------------
# Manual correction
# ---------------------------------------------------------------------------

class CorrectionRequest(BaseModel):
    corrected_by: str = Field(..., description="Username / ID of the person making the correction")
    reason: str       = Field(..., description="Mandatory explanation for the change")

    # Fields the admin can update
    new_punch_in:  Optional[datetime] = None
    new_punch_out: Optional[datetime] = None


class AuditEntry(BaseModel):
    corrected_by: str
    corrected_at: datetime
    reason: str
    old_punch_in:  Optional[datetime]
    old_punch_out: Optional[datetime]
    new_punch_in:  Optional[datetime]
    new_punch_out: Optional[datetime]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class WorkHoursSummary(BaseModel):
    employee_id: str
    total_working_hours: float
    days_present: int
    average_hours_per_day: float
    period_start: str
    period_end: str


class LateArrivalSummary(BaseModel):
    employee_id: str
    date: str
    punch_in: datetime
    expected_time: str
    late_by_minutes: int


class AbsentEmployee(BaseModel):
    employee_id: str
    name: Optional[str] = None


class DepartmentSummaryItem(BaseModel):
    department: str
    total_employees: int
    days_present: int
    average_hours: float


# ---------------------------------------------------------------------------
# Seed / utility
# ---------------------------------------------------------------------------

class EmployeeCreate(BaseModel):
    employee_id: str
    name: str
    department: str
    shift_start: str = Field("09:30", description="Shift start in HH:MM format (IST)")
    shift_end:   str = Field("18:30", description="Shift end   in HH:MM format (IST)")
