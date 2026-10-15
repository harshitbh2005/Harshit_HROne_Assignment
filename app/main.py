"""
Main FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import close_client, get_client
from app.routers.analytics import router as analytics_router
from app.routers.attendance import router as attendance_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up the MongoDB connection on startup
    get_client()
    yield
    # Clean up on shutdown
    await close_client()


app = FastAPI(
    title="Employee Attendance & Analytics API",
    description=(
        "A small but complete attendance tracking service built with FastAPI and MongoDB. "
        "Supports punch-in / punch-out with business-rule validation, admin corrections "
        "with a full audit trail, and several analytics endpoints powered by MongoDB "
        "aggregation pipelines."
    ),
    version="1.0.0",
    contact={
        "name": "Harsh",
        "email": "your-email@example.com",
    },
    lifespan=lifespan,
)

# Allow all origins for demo; in production you'd lock this down.
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
