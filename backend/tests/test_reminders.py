"""Service-level reminder pipeline: target query + notification stamping."""

import asyncio
import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.bot import reminders, service
from app.models import Car, LogEntry, ServiceInterval, User

TODAY = dt.date.today()


def _setup_overdue_interval(db: Session) -> tuple[User, Car, ServiceInterval]:
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

    def __init__(self, failing_chat_ids: set[str]) -> None:
        self.failing_chat_ids = failing_chat_ids
        self.sent: list[tuple[str, str]] = []
        self.markups: list[object] = []

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
        if chat_id in self.failing_chat_ids:
            raise RuntimeError("bot was blocked by the user")
        self.sent.append((chat_id, text))
        self.markups.append(reply_markup)


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




def test_reminder_message_carries_action_buttons(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_session_factory() as db:
        _user, _car, interval = _setup_overdue_interval(db)
        interval_id = interval.id

    monkeypatch.setattr(reminders, "SessionLocal", db_session_factory)
    bot = _FlakyBot(failing_chat_ids=set())
    asyncio.run(reminders.send_due_reminders(bot))

    markup = bot.markups[0]
    assert markup is not None
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "Виконано",
        "Нагадати через 7 днів",
    ]
    assert [button.callback_data for button in buttons] == [
        f"done:{interval_id}",
        f"snooze:{interval_id}",
    ]


def test_reminder_keyboard_names_each_interval_when_several_are_due(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car, first = _setup_overdue_interval(db)
        second = ServiceInterval(
            car_id=car.id, title="Гальмівна рідина", interval_km=60000, last_odometer=1000
        )
        db.add(second)
        db.commit()
        items = [
            service.ReminderItem(car=car, interval=first, computed={}),
            service.ReminderItem(car=car, interval=second, computed={}),
        ]
        markup = reminders.build_reminder_keyboard(items)

    assert [row[0].text for row in markup.inline_keyboard] == [
        "Виконано: Олива двигуна",
        "Виконано: Гальмівна рідина",
    ]


def test_reminder_keyboard_shortens_long_titles(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car, interval = _setup_overdue_interval(db)
        interval.title = "Заміна оливи та масляного фільтра"
        db.commit()
        items = [
            service.ReminderItem(car=car, interval=interval, computed={}),
            service.ReminderItem(car=car, interval=interval, computed={}),
        ]
        markup = reminders.build_reminder_keyboard(items)

    label = markup.inline_keyboard[0][0].text
    assert label.endswith("…")
    assert len(label) <= len("Виконано: ") + 20


def test_done_button_completes_the_interval_through_the_shared_service(
    db_session_factory: sessionmaker,
) -> None:
    """«Виконано» writes the same history the REST endpoint would."""
    with db_session_factory() as db:
        _user, car, interval = _setup_overdue_interval(db)
        interval.last_notified_at = TODAY
        db.commit()

        completion = service.complete_interval_now(db, interval)

        assert completion.log.type == "maintenance"
        assert completion.log.car_id == car.id
        assert completion.log.odometer == car.current_odometer  # 50000
        assert completion.log.date == TODAY
        assert float(completion.log.total_cost) == 0.0
        assert completion.log.maintenance.items == ["Олива двигуна"]
        # The interval starts over and may be reminded about again.
        assert completion.interval.last_odometer == 50000
        assert completion.interval.last_date == TODAY
        assert completion.interval.last_notified_at is None
        assert service.reminder_targets(db, today=TODAY) == []


def test_snooze_button_silences_the_interval_for_its_own_seven_days(
    db_session_factory: sessionmaker,
) -> None:
    """The debt this pays off: «Нагадати через 7 днів» used to only stamp
    last_notified_at — byte for byte what an ordinary reminder already does,
    so the button promised nothing the 7-day cooldown did not already give.
    Now it books a date of its own.
    """
    with db_session_factory() as db:
        _user, _car, interval = _setup_overdue_interval(db)
        assert service.reminder_targets(db, today=TODAY) != []

        service.snooze_interval(db, interval, today=TODAY)

        assert interval.snoozed_until == TODAY + dt.timedelta(days=7)
        # Silenced for the promised seven days...
        for offset in range(0, 8):
            day = TODAY + dt.timedelta(days=offset)
            assert service.reminder_targets(db, today=day) == [], day
        # ...and back on the eighth.
        assert service.reminder_targets(db, today=TODAY + dt.timedelta(days=8)) != []
        # Snoozing is not completing: no history is written.
        assert db.execute(select(func.count()).select_from(LogEntry)).scalar_one() == 0


def test_snooze_outlives_the_ordinary_notification_cooldown(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, _car, interval = _setup_overdue_interval(db)
        # Reminded five days ago: the plain cooldown lapses in two more days.
        interval.last_notified_at = TODAY - dt.timedelta(days=5)
        db.commit()

        service.snooze_interval(db, interval, today=TODAY)

        # Day 7 would be free of the cooldown, but the snooze still holds.
        assert service.reminder_targets(db, today=TODAY + dt.timedelta(days=7)) == []
        assert service.reminder_targets(db, today=TODAY + dt.timedelta(days=8)) != []


def test_completing_a_snoozed_interval_clears_the_snooze(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car, interval = _setup_overdue_interval(db)
        service.snooze_interval(db, interval, today=TODAY)
        assert service.reminder_targets(db, today=TODAY) == []

        service.complete_interval_now(db, interval, today=TODAY)

        db.refresh(interval)
        assert interval.snoozed_until is None
        # It is fresh now, so it is quiet on its own merits, not by snooze.
        assert interval.last_odometer == car.current_odometer
