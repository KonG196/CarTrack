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
    plate,
    public,
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
app.include_router(public.router, prefix="/api")
app.include_router(plate.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, object]:
    """Liveness, plus which optional integrations are actually configured.

    Not a probe of the remote services — only of what this instance was told.
    A misconfigured key still shows as enabled here; the point is to make an
    unset one visible without reading logs.
    """
    return {
        "status": "ok",
        "features": {
            "mail": bool(settings.SMTP_HOST),
            "telegram": bool(settings.TELEGRAM_BOT_TOKEN),
            "vision_ocr": bool(settings.GEMINI_API_KEY),
            "plate_lookup": bool(settings.BAZA_GAI_API_KEY),
            "backup_delivery": bool(settings.BACKUP_TELEGRAM_CHAT_ID),
        },
    }
