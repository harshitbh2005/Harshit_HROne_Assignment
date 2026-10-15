"""
main.py

Entry point. Run with: uvicorn app.main:app --reload

I'm using the lifespan context manager instead of on_event("startup") because
that's the recommended way in newer FastAPI versions (on_event is deprecated).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import close_client, get_client
from app.routers.analytics import router as analytics_router
from app.routers.attendance import router as attendance_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_client()  # init the mongo connection on startup
    yield
    await close_client()  # clean shutdown


app = FastAPI(
    title="Employee Attendance & Analytics API",
    description=(
        "Handles employee punch-in/out with business rules, manual corrections "
        "with audit trail, and analytics via MongoDB aggregation pipelines."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# allowing all origins for now since this is just a demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(attendance_router)
app.include_router(analytics_router)


@app.get("/", tags=["Root"], summary="Health check")
async def root():
    return {
        "service": "Employee Attendance & Analytics API",
        "status": "running",
        "docs": "/docs",
    }
