"""Receipt OCR endpoint: photo upload -> recognized refuel fields."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pytesseract import TesseractNotFoundError

from app.auth import get_current_user
from app.config import settings
from app.models import User
from app.schemas import OcrScanResult
from app.services.ocr import extract_text, parse_receipt_text
from app.services.ocr_llm import recognize_receipt_llm

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/scan", response_model=OcrScanResult)
async def scan_receipt(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> OcrScanResult:
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

    try:
        raw_text = extract_text(image_bytes)
    except TesseractNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OCR is unavailable: the tesseract binary is not installed "
                "on the server. Install it with: brew install tesseract "
                "tesseract-lang"
            ),
        )

    parsed = parse_receipt_text(raw_text)
    # Tesseract could not read the money fields (crumpled paper, glare,
    # tiny photo): give the configured vision model a try. Any failure of
    # the fallback keeps the local result — the endpoint must not break
    # because an external API is down.
    if parsed.found_in_text < 2 and settings.GEMINI_API_KEY:
        try:
            llm_parsed = recognize_receipt_llm(
                image_bytes, file.content_type or "image/jpeg"
            )
        except Exception:
            llm_parsed = None
        if llm_parsed is not None and llm_parsed.found_in_text > parsed.found_in_text:
            parsed = llm_parsed
    return OcrScanResult(
        liters=parsed.liters,
        price_per_liter=parsed.price_per_liter,
        total_cost=parsed.total_cost,
        date=parsed.date,
        gas_station=parsed.gas_station,
        raw_text=raw_text,
    )
