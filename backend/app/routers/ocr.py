"""Photo upload -> recognized fields: fuel receipts and service orders."""

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pytesseract import TesseractNotFoundError
from sqlalchemy.orm import Session

from app.auth import require_verified_user
from app.database import get_db
from app.models import User
from app.schemas import OcrScanResult, OcrWorkOrderResult
from app.services.admin_notify import notify_first_ocr
from app.services.ocr_llm import OcrUnavailable, recognize_receipt, recognize_work_order
from app.i18n import t

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_NO_TESSERACT = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail=(
        "OCR is unavailable: the tesseract binary is not installed on the "
        "server. Install it with: brew install tesseract tesseract-lang"
    ),
)

# The vision model is configured but gave no answer (rate-limited / down). A 503
# lets the app tell the user «скан тимчасово недоступний» rather than blame the
# photo — the frontend maps this status to entryForm.scanUnavailable.
def _ocr_unavailable(lang: str = "en") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=t("err.ocrUnavailable", lang),
    )


async def _flag_first_ocr(db: Session, user: User, kind: str) -> None:
    """Fire the owner's first-scan alert, once, without blocking the loop.

    Only the very first successful scan does any work; the flag check keeps every
    later scan free of a DB write or a thread hop. The send itself (SMTP) runs
    off the event loop, mirroring how the scan above is offloaded.
    """
    if user.admin_notified_first_ocr:
        return
    await asyncio.to_thread(notify_first_ocr, db, user, kind)


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
    current_user: User = Depends(require_verified_user),
    db: Session = Depends(get_db),
) -> OcrScanResult:
    image_bytes = await _read_image(file)
    try:
        # Off the event loop: OCR is CPU + a remote call, and running it inline
        # froze every other request until the scan finished.
        parsed = await asyncio.to_thread(
            recognize_receipt, image_bytes, file.content_type or "image/jpeg", current_user.language
        )
    except TesseractNotFoundError:
        raise _NO_TESSERACT
    except OcrUnavailable:
        raise _ocr_unavailable(current_user.language)

    await _flag_first_ocr(db, current_user, "чек")
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
    current_user: User = Depends(require_verified_user),
    db: Session = Depends(get_db),
) -> OcrWorkOrderResult:
    image_bytes = await _read_image(file)
    try:
        parsed = await asyncio.to_thread(
            recognize_work_order, image_bytes, file.content_type or "image/jpeg", current_user.language
        )
    except TesseractNotFoundError:
        raise _NO_TESSERACT
    except OcrUnavailable:
        raise _ocr_unavailable(current_user.language)

    await _flag_first_ocr(db, current_user, "замовлення-наряд")
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
