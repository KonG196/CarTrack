"""Bot service layer: forward-only odometer and quick-expense defaults."""

import datetime as dt

from sqlalchemy.orm import Session, sessionmaker

from app.bot import service
from app.models import Car, ServiceInterval, User


def test_interval_line_hides_slack_axis_when_overdue() -> None:
    # Overdue on time (596 days) while the odometer still has slack (+10 873 km):
    # only the overdue axis is reported, never "залишилось 10 873 км".
    line = service.format_interval_line(
        ServiceInterval(title="Гальмівна рідина"),
        {"km_left": 10873, "days_left": -596, "health_pct": 0.0},
    )
    assert "прострочено на 596 дн." in line
    assert "залишилось" not in line
    assert "10873" not in line


def test_interval_line_reports_overdue_distance() -> None:
    line = service.format_interval_line(
        ServiceInterval(title="Колодки"),
        {"km_left": -1000, "days_left": None, "health_pct": 0.0},
    )
    assert "прострочено на 1000 км" in line


def test_interval_line_shows_both_remaining_when_on_track() -> None:
    line = service.format_interval_line(
        ServiceInterval(title="Олива"),
        {"km_left": 5000, "days_left": 100, "health_pct": 60.0},
    )
    assert "залишилось 5000 км" in line
    assert "залишилось 100 дн." in line


def _make_user_with_car(
    db: Session, email: str = "owner@example.com", odometer: int = 50000
) -> tuple[User, Car]:
    user = User(email=email, hashed_password="x", telegram_chat_id="42")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="Skoda",
        model="Octavia",
        year=2018,
        fuel_type="diesel",
        current_odometer=odometer,
    )
    db.add(car)
    db.commit()
    return user, car


def test_update_odometer_moves_forward(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _user, car = _make_user_with_car(db)
        result = service.update_odometer(db, car.id, 51000)
        assert result is not None
        assert result.updated is True
        assert (result.old_odometer, result.new_odometer) == (50000, 51000)
        db.refresh(car)
        assert car.current_odometer == 51000


def test_update_odometer_refuses_backward_value(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car = _make_user_with_car(db)
        result = service.update_odometer(db, car.id, 49999)
        assert result is not None
        assert result.updated is False
        assert result.new_odometer == 50000
        db.refresh(car)
        assert car.current_odometer == 50000  # untouched


def test_update_odometer_allows_equal_value(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _user, car = _make_user_with_car(db)
        result = service.update_odometer(db, car.id, 50000)
        assert result is not None
        assert result.updated is True
        db.refresh(car)
        assert car.current_odometer == 50000


def test_update_odometer_unknown_car_returns_none(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        assert service.update_odometer(db, car_id=12345, value=1000) is None


def test_quick_expense_uses_today_and_current_odometer(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car = _make_user_with_car(db)
        log = service.create_quick_expense(db, car.id, "мийка", 300)
        assert log is not None
        assert log.type == "expense"
        assert log.date == dt.date.today()
        assert log.odometer == 50000  # the car's current odometer
        assert float(log.total_cost) == 300.0
        assert log.notes == "мийка"
