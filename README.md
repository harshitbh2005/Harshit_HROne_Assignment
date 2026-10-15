# Employee Attendance & Analytics API

A small FastAPI + MongoDB service that handles employee punch-in / punch-out, manual corrections with an audit trail, and analytics.

---

## What's here

```
├── app/
│   ├── main.py        — FastAPI app, lifespan handler, CORS
│   ├── database.py    — Motor client and collection helpers
│   ├── models.py      — Pydantic request / response schemas
│   ├── services.py    — Business logic (punch rules, late detection, corrections)
│   └── routers/
│       ├── attendance.py — /attendance/* endpoints
│       └── analytics.py  — /analytics/* endpoints
├── requirements.txt
├── README.md
├── REVIEW.md
└── DECISIONS.md
```

---

## Running locally

**Prerequisites:** Python 3.11+, MongoDB 6.0+ running on `localhost:27017`

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set environment variables
# MONGO_URL defaults to mongodb://localhost:27017
# DB_NAME   defaults to hrone_attendance
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=hrone_attendance

# 4. Start the server
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive Swagger UI.

---

## Quick-start walkthrough

```bash
# 1. Register an employee
curl -X POST http://localhost:8000/attendance/employees \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"EMP001","name":"Alice","department":"Engineering","shift_start":"09:30","shift_end":"18:30"}'

# 2. Punch in
curl -X POST http://localhost:8000/attendance/punch-in \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"EMP001"}'

# 3. Punch out
curl -X POST http://localhost:8000/attendance/punch-out \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"EMP001"}'

# 4. Working-hours summary for October 2026
curl "http://localhost:8000/analytics/hours/EMP001?year=2026&month=10"

# 5. Late arrivals in October
curl "http://localhost:8000/analytics/late-arrivals?start_date=2026-10-01&end_date=2026-10-31"

# 6. Who was absent on a specific date?
curl "http://localhost:8000/analytics/absent/2026-10-15"

# 7. Department summary for October
curl "http://localhost:8000/analytics/department-summary?year=2026&month=10"
```

---

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/` | Health check |
| POST | `/attendance/employees` | Register an employee |
| GET  | `/attendance/employees` | List all employees |
| POST | `/attendance/punch-in` | Record punch-in |
| POST | `/attendance/punch-out` | Record punch-out |
| PATCH | `/attendance/records/{id}/correct` | Admin correction with audit |
| GET  | `/attendance/records/{id}` | Fetch a single record |
| GET  | `/attendance/records` | List records (filterable) |
| GET  | `/analytics/hours/{employee_id}` | Monthly working-hours summary |
| GET  | `/analytics/late-arrivals` | Late arrivals in a date range |
| GET  | `/analytics/absent/{date}` | Absent employees on a date |
| GET  | `/analytics/department-summary` | Department-level attendance stats |
| GET  | `/analytics/employee-report/{id}` | Full monthly breakdown per employee |

---

## Business rules

- **No double punch-in** — a second punch-in on the same day is rejected with HTTP 400.
- **Punch-out before punch-in** — rejected with HTTP 400.
- **Late detection** — punch-in more than 15 minutes after shift start → status `LATE`.
- **Half-day** — working hours less than 4 → status `HALF_DAY` (unless already `LATE`).
- **Manual corrections** — any change is appended to an `audit_trail` array in the document (who changed it, when, old values, new values, reason).

---

## Known gaps / what's missing

- **Authentication / authorisation** — there is no JWT or session layer. The `corrected_by` field in the correction endpoint is caller-supplied. In production this would come from a verified token.
- **Soft-delete for corrections** — currently you can override a punch time. A future improvement would be to keep the original record immutable and layer corrections on top.
- **Overnight shifts** — punch-out on the next calendar day is not handled; both events must fall on the same IST date.
- **Automated tests** — I didn't include a test suite due to time constraints, but the business logic in `services.py` is isolated from the database layer making it straightforward to test with pytest + mongomock.

---

## Seed data

No seed script is included. Use the `POST /attendance/employees` endpoint to add employees before punching in. The quick-start commands above demonstrate this flow.
