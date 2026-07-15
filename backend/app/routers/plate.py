"""Vehicle lookup by plate or VIN."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import get_current_user
from app.models import User
from app.ratelimit import RateLimiter, client_ip
from app.schemas import PlateLookupIn, PlateLookupOut
from app.services import plate as plate_service

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
            detail="Пошук за номером не налаштований на цьому сервері.",
        )
    key = (client_ip(request), current_user.id)
    if not lookup_limiter.check(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Забагато запитів. Спробуйте пізніше.",
            headers={"Retry-After": str(lookup_limiter.retry_after(key))},
        )

    try:
        found = plate_service.lookup(payload.query, by_vin=payload.by_vin)
    except plate_service.LookupUnavailable:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Сервіс пошуку тимчасово недоступний.",
        )
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Авто з таким номером не знайдено в реєстрі.",
        )
    return PlateLookupOut(**found)
