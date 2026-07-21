"""Tyre-age arithmetic and the once-a-year mounted-set age nudge."""

import datetime as dt

from sqlalchemy.orm import Session, sessionmaker

from app.bot import service
from app.models import Car, TireSet, User
from app.services.tires import TIRE_AGE_WARN_YEARS, is_tire_age_due, tire_age_years

TODAY = dt.date(2026, 7, 21)


def test_tire_age_years() -> None:
    assert tire_age_years(2019, None, TODAY) == 7  # DOT production year
    assert tire_age_years(None, dt.date(2018, 1, 1), TODAY) == 8  # purchase fallback
    assert tire_age_years(2024, dt.date(2010, 1, 1), TODAY) == 2  # DOT wins over purchase
    assert tire_age_years(None, None, TODAY) is None
    assert tire_age_years(2030, None, TODAY) == 0  # future year is never negative


def test_is_tire_age_due() -> None:
    assert is_tire_age_due(TIRE_AGE_WARN_YEARS) is True
    assert is_tire_age_due(TIRE_AGE_WARN_YEARS - 1) is False
    assert is_tire_age_due(None) is False


def _owner_with_mounted(db: Session, *, dot_year: int | None, installed: bool = True) -> tuple[Car, TireSet]:
    user = User(email="age@example.com", hashed_password="x", telegram_chat_id="9")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="VW",
        model="Golf",
        year=2016,
        fuel_type="diesel",
        current_odometer=100000,
    )
    db.add(car)
    db.flush()
    tire_set = TireSet(
        car_id=car.id, name="set", season="summer", is_installed=installed, dot_year=dot_year
    )
    db.add(tire_set)
    db.commit()
    return car, tire_set


def test_old_mounted_set_targeted_then_deduped(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _car, tire_set = _owner_with_mounted(db, dot_year=2018)  # 8 years -> due
        targets = service.tire_age_reminder_targets(db, today=TODAY)
        assert len(targets) == 1
        _user, reminder = targets[0]
        assert reminder.tire_set.id == tire_set.id
        assert reminder.age_years == 8
        # Stamped for this year -> not sent again until next year.
        service.stamp_tire_age(db, tire_set, TODAY.year)
        assert service.tire_age_reminder_targets(db, today=TODAY) == []


def test_young_set_not_targeted(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _owner_with_mounted(db, dot_year=2024)  # 2 years
        assert service.tire_age_reminder_targets(db, today=TODAY) == []


def test_age_nudge_gated_by_notify_seasonal(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        car, _tire_set = _owner_with_mounted(db, dot_year=2018)
        user = db.get(User, car.user_id)
        user.notify_seasonal = False
        db.commit()
        assert service.tire_age_reminder_targets(db, today=TODAY) == []


def test_shelf_set_not_nudged(db_session_factory: sessionmaker) -> None:
    # Only the mounted set is checked — an old set on the shelf is not nagged.
    with db_session_factory() as db:
        _owner_with_mounted(db, dot_year=2015, installed=False)
        assert service.tire_age_reminder_targets(db, today=TODAY) == []
