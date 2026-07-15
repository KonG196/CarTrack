"""VIN decoding endpoint (offline table, see services/vin.py)."""

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models import User
from app.schemas import VinDecodeIn, VinDecodeOut
from app.services.vin import decode_vin

router = APIRouter(prefix="/vin", tags=["vin"])


@router.post("/decode", response_model=VinDecodeOut)
def decode(
    payload: VinDecodeIn,
    current_user: User = Depends(get_current_user),
) -> VinDecodeOut:
    return VinDecodeOut(**decode_vin(payload.vin))
