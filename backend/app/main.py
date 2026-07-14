"""Kapot Tracker API application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.migrations import ensure_schema
from app.routers import analytics, auth, cars, intervals, logs, ocr, telegram


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup, then apply additive migrations."""
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
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
app.include_router(logs.router, prefix="/api")
app.include_router(intervals.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(telegram.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
