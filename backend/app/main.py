"""Kapot Tracker API application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.migrations import run_migrations
from app.routers import (
    analytics,
    auth,
    cars,
    documents,
    export,
    intervals,
    logs,
    members,
    obd,
    ocr,
    photos,
    reports,
    specs,
    telegram,
    tires,
    vin,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations(engine)
    yield


app = FastAPI(title="Kapot Tracker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(cars.router, prefix="/api")
app.include_router(members.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(intervals.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(telegram.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(vin.router, prefix="/api")
app.include_router(specs.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(obd.router, prefix="/api")
app.include_router(tires.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
