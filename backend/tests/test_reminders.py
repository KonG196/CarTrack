"""Service-level reminder pipeline: target query + notification stamping."""

import asyncio
import datetime as dt

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.bot import reminders, service
from app.models import Car, LogEntry, ServiceInterval, User

TODAY = dt.date.today()


def _setup_overdue_interval(db: Session) -> tuple[User, Car, ServiceInterval]:
    """A linked user with one car whose oil-change interval is overdue."""
    user = User(
        email="linked@example.com", hashed_password="x", telegram_chat_id="42"
    )
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="Skoda",
        model="Octavia",
        year=2018,
        fuel_type="diesel",
        current_odometer=50000,
    )
    db.add(car)
    db.flush()
    # due at 49000 km, car is at 50000 km -> overdue by 1000 km
    interval = ServiceInterval(
        car_id=car.id, title="Олива двигуна", interval_km=10000, last_odometer=39000
    )
    db.add(interval)
    db.commit()
    return user, car, interval


def test_overdue_interval_is_targeted_then_stamped_then_excluded(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        user, car, interval = _setup_overdue_interval(db)

        targets = service.reminder_targets(db, today=TODAY)
        assert len(targets) == 1
        target_user, items = targets[0]
        assert target_user.id == user.id
        assert [item.interval.id for item in items] == [interval.id]
        assert items[0].car.id == car.id
        assert items[0].computed["status"] == "overdue"

        service.stamp_notified(db, [interval.id], today=TODAY)
        db.refresh(interval)
        assert interval.last_notified_at == TODAY

        # freshly notified -> excluded from the next run
        assert service.reminder_targets(db, today=TODAY) == []


def test_unlinked_user_is_not_targeted(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, _car, _interval = _setup_overdue_interval(db)
        user.telegram_chat_id = None
        db.commit()

        assert service.reminder_targets(db, today=TODAY) == []


def test_stale_notification_is_renotified(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _user, _car, interval = _setup_overdue_interval(db)
        interval.last_notified_at = TODAY - dt.timedelta(days=8)
        db.commit()

        targets = service.reminder_targets(db, today=TODAY)
        assert len(targets) == 1

        interval.last_notified_at = TODAY - dt.timedelta(days=3)
        db.commit()
        assert service.reminder_targets(db, today=TODAY) == []


def test_healthy_interval_is_not_targeted(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _user, car, interval = _setup_overdue_interval(db)
        interval.last_odometer = car.current_odometer  # just serviced -> ok
        db.commit()

        assert service.reminder_targets(db, today=TODAY) == []


class _FlakyBot:
    """Fake aiogram Bot: raises for the given chat ids, records the rest."""

    def __init__(self, failing_chat_ids: set[str]) -> None:
        self.failing_chat_ids = failing_chat_ids
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> None:
        if chat_id in self.failing_chat_ids:
            raise RuntimeError("bot was blocked by the user")
        self.sent.append((chat_id, text))


def test_send_due_reminders_isolates_per_user_failures(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One user's failed send must not stop others nor stamp their intervals."""
    with db_session_factory() as db:
        _user1, _car1, interval1 = _setup_overdue_interval(db)  # chat id "42"
        user2 = User(
            email="second@example.com", hashed_password="x", telegram_chat_id="43"
        )
        db.add(user2)
        db.flush()
        car2 = Car(
            user_id=user2.id,
            brand="Renault",
            model="Megane",
            year=2016,
            fuel_type="petrol",
            current_odometer=90000,
        )
        db.add(car2)
        db.flush()
        interval2 = ServiceInterval(
            car_id=car2.id, title="Свічки", interval_km=20000, last_odometer=60000
        )
        db.add(interval2)
        db.commit()
        interval1_id, interval2_id = interval1.id, interval2.id

    monkeypatch.setattr(reminders, "SessionLocal", db_session_factory)
    bot = _FlakyBot(failing_chat_ids={"42"})

    # must not raise even though the first user's send blows up
    asyncio.run(reminders.send_due_reminders(bot))

    assert [chat_id for chat_id, _text in bot.sent] == ["43"]
    with db_session_factory() as db:
        failed = db.get(ServiceInterval, interval1_id)
        notified = db.get(ServiceInterval, interval2_id)
        assert failed is not None and failed.last_notified_at is None
        assert notified is not None and notified.last_notified_at == dt.date.today()


def test_latest_log_date_across_cars(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, car, _interval = _setup_overdue_interval(db)
        assert service.latest_log_date(db, user) is None

        db.add(
            LogEntry(
                car_id=car.id,
                type="expense",
                odometer=car.current_odometer,
                date=TODAY - dt.timedelta(days=10),
                total_cost=100,
            )
        )
        db.commit()
        assert service.latest_log_date(db, user) == TODAY - dt.timedelta(days=10)
