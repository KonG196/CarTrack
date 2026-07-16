"""Tokenless public routes — the QR passport, and nothing that isn't public.

Deliberately its own router with no auth dependency and no access checks: the
token IS the authorization, and the response is limited to the passport fields.
Never widen what a car exposes here without weighing that it is world-readable.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Car
from app.schemas import PublicCarPassport

router = APIRouter(tags=["public"])


@router.get("/public/cars/{token}", response_model=PublicCarPassport)
def public_car_passport(token: str, db: Session = Depends(get_db)) -> PublicCarPassport:
    """The car behind a passport token, or 404 for a wrong or revoked one."""
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    car = db.execute(
        select(Car).where(Car.public_token == token)
    ).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return PublicCarPassport(
        brand=car.brand,
        model=car.model,
        generation=car.generation,
        engine=car.engine,
        year=car.year,
        plate=car.plate,
        vin=car.vin,
        fuel_type=car.fuel_type,
        contact_phone=car.contact_phone,
        insurance_number=car.insurance_number,
        insurance_until=car.insurance_until,
        tire_pressure=car.tire_pressure,
        fuel_approval=car.fuel_approval,
    )
