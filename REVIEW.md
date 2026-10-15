# REVIEW.md

This file reviews a hypothetical (but representative) piece of attendance-related Python code and points out what I'd change and why.

---

## The Code Under Review

```python
import pymongo
from datetime import datetime

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["attendance"]

def mark_attendance(emp_id, punch_type):
    now = datetime.now()
    db.logs.insert_one({
        "emp_id": emp_id,
        "punch": punch_type,
        "time": now
    })
    return True
```

---

## Issues I Found

### 1. Global MongoClient — not wrong, but fragile

The client is created at module import time with no error handling. If MongoDB is down when the service starts, the import itself explodes rather than giving a useful startup error. Better to create the client lazily or inside an application-lifespan hook so you control the failure mode.

### 2. `datetime.now()` returns naive datetimes

`datetime.now()` produces a timezone-naive object. When you query MongoDB from a different timezone or across machines, you lose track of *which* timezone the timestamp belongs to. You should use `datetime.now(timezone.utc)` or `datetime.now(ZoneInfo("Asia/Kolkata"))` to keep the offset explicit.

### 3. No duplicate-punch validation

The function will happily insert two consecutive `"IN"` records for the same employee. There is no check like "what was the last punch type for this employee today?" A real attendance system must reject or at least warn on this.

### 4. No return value beyond `True`

The inserted document ID is thrown away. Callers have no way to reference the specific record for corrections or auditing later.

### 5. Missing index on `(emp_id, time)`

For any query like "give me all punches by employee X this month" MongoDB will do a full collection scan once the dataset grows. A compound index on `{"employee_id": 1, "date": 1}` turns those queries from O(n) to O(log n).

### 6. No error handling around the insert

If the database is momentarily unreachable, `insert_one` raises `pymongo.errors.ServerSelectionTimeoutError`. The caller gets an unhandled exception rather than a meaningful HTTP 503. The function should catch `PyMongoError` and re-raise as something the API layer can translate to a proper error response.

---

## What I'd Keep

The function is short and does exactly one thing. That's a good instinct — side-effect functions should be narrow. I'd preserve that principle and just layer on the fixes above.
