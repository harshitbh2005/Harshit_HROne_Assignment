# DECISIONS.md

A write-up of the non-obvious design choices I made while building this service.

---

## 1. Motor over PyMongo (async vs sync)

FastAPI is built on top of Starlette's ASGI event loop. If you use the synchronous PyMongo driver inside an async route, every database call blocks the event loop and you lose the concurrency benefit entirely. Motor is PyMongo's official async wrapper — same API, same aggregation syntax, but it yields control back to the event loop while waiting on I/O. For a tiny project the difference is invisible, but getting into the habit matters.

---

## 2. Single `attendance_logs` collection rather than separate punch-in / punch-out collections

I toyed with two collections — one per punch type — but that makes most queries harder. "How many hours did this employee work on Monday?" becomes a join. With a single document per employee-day that stores both `punch_in` and `punch_out`, the query is just a `$match` + a subtraction. MongoDB's aggregation operators like `$subtract` on two date fields are fast and clean.

---

## 3. Storing `date` as a plain ISO string (`"2026-10-15"`)

MongoDB can store dates as BSON dates, and range queries work on both. I chose the plain string because:

- It indexes efficiently (lexicographic order matches calendar order for ISO-8601).
- Timezone headaches disappear at the partition boundary — "today" in IST doesn't accidentally bleed into the next UTC day.
- It's human-readable in any MongoDB GUI without converting.

The trade-off is that date arithmetic (`$dateAdd`, etc.) can't operate on plain strings, but I don't need that in this project.

---

## 4. Audit trail as an embedded array, not a separate collection

Each correction is appended to the document's `audit_trail` array. I considered a separate `corrections` collection with a foreign key back to the attendance record, but for this scale there is no benefit and two collections means two round-trips for every "show me this record with its history" query. MongoDB is good at embedding related data.

The only scenario where a separate collection wins is if audit entries become very large or need their own query patterns — neither applies here.

---

## 5. IST everywhere, UTC in the DB

All business logic computes in IST using Python's `zoneinfo` module. Timestamps are stored as timezone-aware datetimes — Motor serialises them to UTC BSON dates automatically. This means the database layer is always in UTC (a safe default), but the business layer reasons in IST (which is where our employees are). Converting at the boundary is explicit and easy to trace.

---

## 6. Why no authentication?

I deliberately left authentication out of scope. Adding it would mean either:

- A full JWT setup (adds `python-jose`, key management, refresh-token logic) — easily an extra few hours.
- A fake header-based scheme — misleading because it looks secure but isn't.

The `corrected_by` field in the correction endpoint is a string the caller provides, which in production would come from a decoded JWT claim. I noted this in the README as a known gap rather than papering over it.

---

## 7. Not using FastAPI's dependency injection for the DB

I could have done:

```python
async def get_db():
    return motor_client["hrone_attendance"]

@router.post("/punch-in")
async def punch_in(db = Depends(get_db)):
    ...
```

I chose module-level collection helpers instead because for Motor there is only one client for the lifetime of the app — injecting it per-request is misleading (it suggests a new connection per request, which isn't the case). The approach I used is simpler to explain in a live review.
