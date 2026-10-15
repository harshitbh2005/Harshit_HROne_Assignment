"""
models.py - all the pydantic schemas in one place

I kept everything flat here instead of splitting into multiple files.
For a project this size it's easier to just scroll than to jump between files.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class PyObjectId(str):
    # needed to make MongoDB's ObjectId work with pydantic without extra libraries
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return str(v)


# --- punch request/response ---

class PunchRequest(BaseModel):
    employee_id: str = Field(..., description="e.g. EMP001")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="leave empty and we'll use server time"
    )
    notes: Optional[str] = Field(None, description="optional note from employee")


class PunchResponse(BaseModel):
    status: str
    employee_id: str
    punch_type: Literal["IN", "OUT"]
    timestamp: datetime
    record_id: str


# --- for the manual correction endpoint ---

class CorrectionRequest(BaseModel):
    corrected_by: str = Field(..., description="who is making this change")
    reason: str       = Field(..., description="why - this goes into the audit trail")

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


# --- analytics response shapes ---

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


# --- used when registering a new employee ---

class EmployeeCreate(BaseModel):
    employee_id: str
    name: str
    department: str
    shift_start: str = Field("09:30", description="HH:MM in IST")
    shift_end:   str = Field("18:30", description="HH:MM in IST")
