"""Photo upload -> recognized fields: fuel receipts and service orders."""

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pytesseract import TesseractNotFoundError

from app.auth import get_current_user
from app.models import User
from app.schemas import OcrScanResult, OcrWorkOrderResult
from app.services.ocr_llm import recognize_receipt, recognize_work_order

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_NO_TESSERACT = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail=(
        "OCR is unavailable: the tesseract binary is not installed on the "
        "server. Install it with: brew install tesseract tesseract-lang"
    ),
)


async def _read_image(file: UploadFile) -> bytes:
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only image uploads are supported",
        )
    too_large = HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail="Image is too large (max 10 MB)",
    )
    # Enforce the cap before pulling the whole upload into memory: check the
    # size Starlette recorded while spooling, then read at most one byte over
    # the limit so an unreported size still cannot blow up memory.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise too_large
    image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise too_large
    return image_bytes


@router.post("/scan", response_model=OcrScanResult)
async def scan_receipt(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> OcrScanResult:
    image_bytes = await _read_image(file)
    try:
        # Off the event loop: OCR is CPU + a remote call, and running it inline
        # froze every other request until the scan finished.
        parsed = await asyncio.to_thread(
            recognize_receipt, image_bytes, file.content_type or "image/jpeg"
        )
    except TesseractNotFoundError:
        raise _NO_TESSERACT

    return OcrScanResult(
        liters=parsed.liters,
        price_per_liter=parsed.price_per_liter,
        total_cost=parsed.total_cost,
        date=parsed.date,
        gas_station=parsed.gas_station,
        raw_text=parsed.raw_text,
    )


@router.post("/scan-order", response_model=OcrWorkOrderResult)
async def scan_work_order(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> OcrWorkOrderResult:
    image_bytes = await _read_image(file)
    try:
        parsed = await asyncio.to_thread(
            recognize_work_order, image_bytes, file.content_type or "image/jpeg"
        )
    except TesseractNotFoundError:
        raise _NO_TESSERACT

    date = None
    if parsed.date:
        try:
            date = dt.date.fromisoformat(parsed.date)
        except ValueError:
            date = None
    # A shop cannot invoice work it has not done, so a future date is a misread
    # — usually a «2028» that was «2023».
    if date and date > dt.date.today():
        date = None

    return OcrWorkOrderResult(
        items=parsed.items,
        parts_cost=parsed.parts_cost,
        labor_cost=parsed.labor_cost,
        total_cost=parsed.total_cost,
        date=date,
        confident=parsed.confident,
        raw_text=parsed.raw_text,
    )
