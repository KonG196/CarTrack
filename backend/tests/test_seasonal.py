"""Seasonal autumn reminders: plate→zone map and the once-a-season targeting."""

import datetime as dt

from sqlalchemy.orm import Session, sessionmaker

from app.bot import service
from app.models import Car, TireSet, User
from app.services import climate


def test_plate_zone_by_second_letter() -> None:
    assert climate.plate_zone("AC1234BB") == climate.ZONE_WEST  # Волинська
    assert climate.plate_zone("AT5678XX") == climate.ZONE_WEST  # Івано-Франківськ
    assert climate.plate_zone("AA0001AA") == climate.ZONE_CENTER  # Київ
    assert climate.plate_zone("AE9999HH") == climate.ZONE_SOUTH_EAST  # Дніпро
    # Cyrillic input folds to the same code.
    assert climate.plate_zone("АЕ9999НН") == climate.ZONE_SOUTH_EAST
    # No/garbage plate falls to the central calendar.
    assert climate.plate_zone(None) == climate.ZONE_CENTER
    assert climate.plate_zone("") == climate.ZONE_CENTER


def test_windows_open_on_the_zone_date() -> None:
    # West tyres start 8 Oct; on the day it is due, the day before it is not.
    assert climate.tire_changeover_due("AC1234BB", dt.date(2026, 10, 8)) is True
    assert climate.tire_changeover_due("AC1234BB", dt.date(2026, 10, 7)) is False
    # South-east starts later (25 Oct), so 8 Oct is too early there.
    assert climate.tire_changeover_due("AE1234HH", dt.date(2026, 10, 8)) is False
    assert climate.tire_changeover_due("AE1234HH", dt.date(2026, 10, 25)) is True
    # The window closes after a fortnight.
    assert climate.tire_changeover_due("AC1234BB", dt.date(2026, 10, 22)) is True
    assert climate.tire_changeover_due("AC1234BB", dt.date(2026, 10, 23)) is False


def _owner_with_car(db: Session, *, plate: str, season: str | None) -> Car:
    user = User(email="s@example.com", hashed_password="x", telegram_chat_id="7")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="Skoda",
        model="Octavia",
        year=2018,
        fuel_type="petrol",
        current_odometer=50000,
        plate=plate,
    )
    db.add(car)
    db.flush()
    if season is not None:
        db.add(
            TireSet(
                car_id=car.id, name="set", season=season, is_installed=True
            )
        )
    db.commit()
    return car


def test_tire_and_washer_targets_then_dedup(db_session_factory: sessionmaker) -> None:
    # West plate, on summer tyres. 20 Oct is inside both the tyre (8-22) and the
    # washer (20-...) windows, so both nudges are due.
    day = dt.date(2026, 10, 20)
    with db_session_factory() as db:
        car = _owner_with_car(db, plate="AC1234BB", season="summer")

        kinds = {r.kind for _u, r in service.seasonal_reminder_targets(db, today=day)}
        assert kinds == {"tires", "washer"}

        service.stamp_seasonal(db, car, "tires", day.year)
        service.stamp_seasonal(db, car, "washer", day.year)
        # Both already fired this year — nothing left to send.
        assert service.seasonal_reminder_targets(db, today=day) == []


def test_no_tire_nudge_on_winter_tyres(db_session_factory: sessionmaker) -> None:
    day = dt.date(2026, 10, 10)  # inside the west tyre window, before washer
    with db_session_factory() as db:
        _owner_with_car(db, plate="AC1234BB", season="winter")
        kinds = {r.kind for _u, r in service.seasonal_reminder_targets(db, today=day)}
        assert "tires" not in kinds


def test_no_nudge_when_seasonal_off(db_session_factory) -> None:
    day = dt.date(2026, 10, 20)
    with db_session_factory() as db:
        car = _owner_with_car(db, plate="AC1234BB", season="summer")
        user = db.get(User, car.user_id)
        user.notify_seasonal = False
        db.commit()
        assert service.seasonal_reminder_targets(db, today=day) == []


def test_changeover_season_both_windows() -> None:
    # Central plate: autumn window Oct 15-29 -> winter, spring window Apr 1-15
    # -> summer, everything else None.
    assert climate.tire_changeover_season("AA0001AA", dt.date(2026, 10, 16)) == "winter"
    assert climate.tire_changeover_season("AA0001AA", dt.date(2026, 4, 2)) == "summer"
    assert climate.tire_changeover_season("AA0001AA", dt.date(2026, 7, 1)) is None


def test_add_tires_nudge_when_car_has_no_sets(db_session_factory) -> None:
    # A car with zero tire sets gets the «set up your tyres» CTA nudge instead of
    # nothing, once per autumn (deduped via the shared tire_reminder_year stamp).
    day = dt.date(2026, 10, 10)  # west tyre window, before the washer window
    with db_session_factory() as db:
        car = _owner_with_car(db, plate="AC1234BB", season=None)  # no TireSet rows
        kinds = {r.kind for _u, r in service.seasonal_reminder_targets(db, today=day)}
        assert kinds == {"tires_add"}
        service.stamp_seasonal(db, car, "tires_add", day.year)
        assert service.seasonal_reminder_targets(db, today=day) == []
