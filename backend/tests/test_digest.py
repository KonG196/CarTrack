"""The weekly digest: what a quiet week is worth saying, and to whom.

Three promises are pinned here:

* the digest is built from the *week*, not from the car's whole life — the
  numbers a Sunday message quotes are the numbers of the seven days behind it;
* a week with no entries produces nothing at all. Not an empty digest, not a
  «нічого не сталося» — silence. A tracker that messages you about the week
  you did not use it is a tracker you mute;
* it reaches the car's OWNER, once per car, and only while they want it
  (`users.digest_enabled`, `/digest on|off`).

The math itself is never re-checked here: spend comes from
``services.stats.compute_analytics``, consumption from the full-to-full engine
in ``services.fuel``, the nearest ТО from ``services.intervals`` — each pinned
by its own test file. What these tests check is that the digest *asks*.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message
from sqlalchemy.orm import Session, sessionmaker

from app.bot import handlers, reminders, service
from app.models import (
    Car,
    CarMember,
    LogEntry,
    MaintenanceDetails,
    RefuelDetails,
    ServiceInterval,
    User,
)

# A real Sunday, so the weekday gate is exercised for what it is instead of
# whichever day the suite happens to run on.
SUNDAY = dt.date(2026, 7, 12)
MONDAY = SUNDAY - dt.timedelta(days=6)  # the first day of the digest window

OWNER_CHAT = 42
MEMBER_CHAT = 43


# World building


def _user(db: Session, email: str, chat_id: int | None) -> User:
    user = User(
        email=email,
        hashed_password="x",
        telegram_chat_id=None if chat_id is None else str(chat_id),
    )
    db.add(user)
    db.flush()
    return user


def _car(db: Session, owner: User, brand: str, model: str, odometer: int) -> Car:
    car = Car(
        user_id=owner.id,
        brand=brand,
        model=model,
        year=2018,
        fuel_type="diesel",
        current_odometer=odometer,
    )
    db.add(car)
    db.flush()
    db.add(CarMember(car_id=car.id, user_id=owner.id, role="owner"))
    db.flush()
    return car


def _refuel(
    db: Session,
    car: Car,
    *,
    date: dt.date,
    odometer: int,
    liters: float,
    total_cost: float,
) -> LogEntry:
    log = LogEntry(
        car_id=car.id,
        type="refuel",
        odometer=odometer,
        date=date,
        total_cost=Decimal(str(total_cost)),
    )
    db.add(log)
    db.flush()
    db.add(
        RefuelDetails(
            log_entry_id=log.id,
            liters=Decimal(str(liters)),
            price_per_liter=Decimal(str(round(total_cost / liters, 2))),
            is_full_tank=True,
        )
    )
    db.flush()
    return log


def _maintenance(
    db: Session, car: Car, *, date: dt.date, odometer: int, total_cost: float
) -> LogEntry:
    log = LogEntry(
        car_id=car.id,
        type="maintenance",
        odometer=odometer,
        date=date,
        total_cost=Decimal(str(total_cost)),
    )
    db.add(log)
    db.flush()
    db.add(MaintenanceDetails(log_entry_id=log.id, items=["Олива двигуна"]))
    db.flush()
    return log


def _full_week(db: Session) -> tuple[User, Car]:
    """An owner whose week has everything the digest promises to report.

    400 km driven on 26 l between two full tanks (6.5 л/100км), 3 300 ₴ of
    fuel, 700 ₴ of service, and an oil change 600 km away.
    """
    owner = _user(db, "owner@example.com", OWNER_CHAT)
    car = _car(db, owner, "Skoda", "Octavia", odometer=50400)
    _refuel(db, car, date=MONDAY, odometer=50000, liters=40, total_cost=2000)
    _maintenance(db, car, date=SUNDAY - dt.timedelta(days=2), odometer=50300, total_cost=700)
    _refuel(
        db,
        car,
        date=SUNDAY - dt.timedelta(days=1),
        odometer=50400,
        liters=26,
        total_cost=1300,
    )
    db.add(
        ServiceInterval(
            car_id=car.id,
            title="Олива двигуна",
            interval_km=10000,
            last_odometer=41000,  # due at 51000, car is at 50400 -> 600 km left
        )
    )
    db.commit()
    return owner, car


# The text


def test_digest_text_carries_every_block(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _owner, car = _full_week(db)

        text = service.build_weekly_digest(db, car, today=SUNDAY)

    assert text is not None
    assert "📊 Тиждень з Kapot" in text
    assert "Skoda Octavia" in text  # one message per car: it must name itself
    assert "4000.00 ₴" in text  # 2000 + 1300 + 700
    assert "заправки 3300.00 ₴" in text
    assert "ТО 700.00 ₴" in text
    assert "+400 км" in text  # 50400 - 50000
    assert "6.5 л/100км" in text  # 26 l over 400 km
    assert "«Олива двигуна» через 600 км" in text


def test_digest_counts_only_the_seven_days_behind_it(
    db_session_factory: sessionmaker,
) -> None:
    """Last week's spending is last week's; it never leaks into this digest."""
    with db_session_factory() as db:
        _owner, car = _full_week(db)
        # One day older than the window, and priced so it could not hide in a
        # rounding error if it were counted.
        _maintenance(
            db,
            car,
            date=MONDAY - dt.timedelta(days=1),
            odometer=49900,
            total_cost=9999,
        )
        db.commit()

        text = service.build_weekly_digest(db, car, today=SUNDAY)

    assert text is not None
    assert "9999" not in text
    assert "4000.00 ₴" in text


def test_digest_measures_distance_from_the_last_reading_before_the_week(
    db_session_factory: sessionmaker,
) -> None:
    """Km driven is measured against where the car stood on Monday morning —
    an odometer known from *before* the window, not merely the first entry
    inside it. Otherwise the drive up to the week's first refuel is free."""
    with db_session_factory() as db:
        _owner, car = _full_week(db)
        _maintenance(
            db,
            car,
            date=MONDAY - dt.timedelta(days=3),
            odometer=49700,
            total_cost=0,
        )
        db.commit()

        text = service.build_weekly_digest(db, car, today=SUNDAY)

    assert text is not None
    assert "+700 км" in text  # 50400 - 49700


def test_digest_omits_what_the_week_cannot_measure(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        car = _car(db, owner, "Renault", "Megane", odometer=90000)
        _maintenance(db, car, date=SUNDAY, odometer=90000, total_cost=450)
        db.commit()

        text = service.build_weekly_digest(db, car, today=SUNDAY)

    assert text is not None
    assert "450.00 ₴" in text
    assert "л/100км" not in text
    assert "Найближче ТО" not in text


def test_empty_week_produces_no_digest(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _owner, car = _full_week(db)

        # A fortnight on, the same car's week is empty.
        assert service.build_weekly_digest(db, car, today=SUNDAY + dt.timedelta(days=14)) is None


# Targeting


def test_digest_targets_the_owner_once_per_car(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner, car = _full_week(db)
        second = _car(db, owner, "Renault", "Megane", odometer=90000)
        _maintenance(db, second, date=SUNDAY, odometer=90000, total_cost=450)
        db.commit()

        targets = service.digest_targets(db, today=SUNDAY)

        assert len(targets) == 1
        target_user, digests = targets[0]
        assert target_user.id == owner.id
        assert [digest.car.id for digest in digests] == [car.id, second.id]
        assert all(digest.text for digest in digests)


def test_digest_skips_cars_with_an_empty_week(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner, car = _full_week(db)
        _car(db, owner, "Renault", "Megane", odometer=90000)  # no entries at all
        db.commit()

        targets = service.digest_targets(db, today=SUNDAY)

        assert len(targets) == 1
        _target_user, digests = targets[0]
        assert [digest.car.id for digest in digests] == [car.id]


def test_disabled_flag_silences_the_digest(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner, _car = _full_week(db)
        assert owner.digest_enabled is True  # on by default

        owner.digest_enabled = False
        db.commit()

        assert service.digest_targets(db, today=SUNDAY) == []


def test_unlinked_user_is_not_targeted(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner, _car = _full_week(db)
        owner.telegram_chat_id = None
        db.commit()

        assert service.digest_targets(db, today=SUNDAY) == []


def test_a_member_gets_no_digest_about_someone_elses_car(
    db_session_factory: sessionmaker,
) -> None:
    """Owner-only, exactly as reminders are: one car, one owner, one message."""
    with db_session_factory() as db:
        owner, car = _full_week(db)
        member = _user(db, "member@example.com", MEMBER_CHAT)
        db.add(CarMember(car_id=car.id, user_id=member.id, role="editor"))
        db.commit()

        targets = service.digest_targets(db, today=SUNDAY)

        assert [user.id for user, _digests in targets] == [owner.id]


# Sending


class _FlakyBot:

    def __init__(self, failing_chat_ids: set[str] | None = None) -> None:
        self.failing_chat_ids = failing_chat_ids or set()
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
        if chat_id in self.failing_chat_ids:
            raise RuntimeError("bot was blocked by the user")
        self.sent.append((chat_id, text))


def test_digests_are_sent_on_sunday(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_session_factory() as db:
        _full_week(db)

    monkeypatch.setattr(reminders, "SessionLocal", db_session_factory)
    bot = _FlakyBot()
    asyncio.run(reminders.send_weekly_digests(bot, today=SUNDAY))

    assert [chat_id for chat_id, _text in bot.sent] == ["42"]
    assert "📊 Тиждень з Kapot" in bot.sent[0][1]


@pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
def test_no_digest_on_any_other_day(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch, offset: int
) -> None:
    with db_session_factory() as db:
        _full_week(db)

    monkeypatch.setattr(reminders, "SessionLocal", db_session_factory)
    bot = _FlakyBot()
    asyncio.run(
        reminders.send_weekly_digests(bot, today=SUNDAY + dt.timedelta(days=offset))
    )

    assert bot.sent == []


def test_a_failed_send_does_not_stop_the_other_users(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_session_factory() as db:
        _full_week(db)  # chat 42
        other = _user(db, "other@example.com", MEMBER_CHAT)
        car = _car(db, other, "Renault", "Megane", odometer=90000)
        _maintenance(db, car, date=SUNDAY, odometer=90000, total_cost=450)
        db.commit()

    monkeypatch.setattr(reminders, "SessionLocal", db_session_factory)
    bot = _FlakyBot(failing_chat_ids={"42"})
    asyncio.run(reminders.send_weekly_digests(bot, today=SUNDAY))  # must not raise

    assert [chat_id for chat_id, _text in bot.sent] == ["43"]


# /digest on|off


@pytest.fixture()
def replies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    async def fake_answer(self, text: str = "", **kwargs) -> None:
        sent.append(text)

    monkeypatch.setattr(Message, "answer", fake_answer)
    return sent


def _message(chat_id: int) -> Message:
    return Message.model_construct(
        message_id=1,
        date=dt.datetime.now(dt.timezone.utc),
        chat=Chat.model_construct(id=chat_id, type="private"),
        text="/digest",
        photo=None,
    )


def _run_digest_command(chat_id: int, args: str | None) -> None:
    asyncio.run(
        handlers.cmd_digest(
            _message(chat_id),
            CommandObject(prefix="/", command="digest", args=args),
        )
    )


def test_digest_off_then_on(
    db_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    replies: list[str],
) -> None:
    with db_session_factory() as db:
        owner, _car = _full_week(db)
        owner_id = owner.id
    monkeypatch.setattr(handlers, "SessionLocal", db_session_factory)

    _run_digest_command(OWNER_CHAT, "off")
    with db_session_factory() as db:
        assert db.get(User, owner_id).digest_enabled is False
    assert "вимкнено" in replies[-1]

    _run_digest_command(OWNER_CHAT, "on")
    with db_session_factory() as db:
        assert db.get(User, owner_id).digest_enabled is True
    assert "увімкнено" in replies[-1]


def test_bare_digest_command_reports_the_current_state(
    db_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    replies: list[str],
) -> None:
    with db_session_factory() as db:
        owner, _car = _full_week(db)
        owner_id = owner.id
    monkeypatch.setattr(handlers, "SessionLocal", db_session_factory)

    _run_digest_command(OWNER_CHAT, None)

    with db_session_factory() as db:
        assert db.get(User, owner_id).digest_enabled is True  # untouched
    assert "/digest on" in replies[-1]


def test_digest_command_needs_a_linked_account(
    db_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    replies: list[str],
) -> None:
    monkeypatch.setattr(handlers, "SessionLocal", db_session_factory)

    _run_digest_command(999, "off")

    assert replies == [handlers.NOT_LINKED_TEXT]
