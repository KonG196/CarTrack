"""Vehicle lookup by plate or VIN."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import get_current_user
from app.models import User
from app.ratelimit import RateLimiter, client_ip
from app.schemas import PlateLookupIn, PlateLookupOut
from app.services import plate as plate_service
from app.i18n import t

router = APIRouter(tags=["plate"])

# The free tier is ~1000 lookups a month for the whole instance, so one user
# cannot be allowed to spend it in an afternoon.
lookup_limiter = RateLimiter(limit=10, window_seconds=60 * 60)


@router.post("/plate/lookup", response_model=PlateLookupOut)
def lookup_plate(
    payload: PlateLookupIn,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> PlateLookupOut:
    if not plate_service.enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=t("err.plateNotConfigured", current_user.language),
        )
    key = (client_ip(request), current_user.id)
    if not lookup_limiter.check(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=t("err.tooManyRequests", current_user.language),
            headers={"Retry-After": str(lookup_limiter.retry_after(key))},
        )

    try:
        found = plate_service.lookup(payload.query, by_vin=payload.by_vin)
    except plate_service.LookupUnavailable:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=t("err.plateServiceUnavailable", current_user.language),
        )
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("err.plateNotFound", current_user.language),
        )
    return PlateLookupOut(**found)
