"""The bot under sharing: shared cars, entry authorship, owner-only reminders.

Three promises are pinned here:

* the bot's garage is the *accessible* garage — owned cars plus shared ones,
  the shared ones visibly marked so nobody logs a refuel to the wrong car;
* every entry the bot writes carries its author, so a shared car's history
  says who did what;
* reminders reach the owner and nobody else (see ``reminder_targets``).

Access itself is never re-implemented here — the handlers lean on
``app.access``, which ``test_access.py`` pins cell by cell. What these tests
check is that the bot *asks*.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.bot import handlers, service
from app.models import Car, CarMember, LogEntry, ServiceInterval, User

TODAY = dt.date.today()

OWNER_CHAT = 42
MEMBER_CHAT = 43


# Fixtures


@pytest.fixture()
def bot_db(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> sessionmaker:
    monkeypatch.setattr(handlers, "SessionLocal", db_session_factory)
    return db_session_factory


@pytest.fixture()
def replies(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []

    async def fake_answer(self, text: str = "", **kwargs) -> None:
        sent.append({"text": text, "reply_markup": kwargs.get("reply_markup")})

    async def fake_answer_document(self, document, **kwargs) -> None:
        sent.append({"document": document, "caption": kwargs.get("caption")})

    async def fake_callback_answer(self, text: str | None = None, **kwargs) -> None:
        sent.append({"callback_answer": text})

    monkeypatch.setattr(Message, "answer", fake_answer)
    monkeypatch.setattr(Message, "answer_document", fake_answer_document)
    monkeypatch.setattr(CallbackQuery, "answer", fake_callback_answer)
    return sent


def _user(db: Session, email: str, chat_id: int | None) -> User:
    user = User(
        email=email,
        hashed_password="x",
        telegram_chat_id=None if chat_id is None else str(chat_id),
    )
    db.add(user)
    db.flush()
    return user


def _car(db: Session, owner: User, brand: str, model: str, odometer: int = 50000) -> Car:
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
    # The owner membership row the API writes on create; access never depends
    # on it, but the bot must not double-count it into the garage either.
    db.add(CarMember(car_id=car.id, user_id=owner.id, role="owner"))
    db.flush()
    return car


def _share(db: Session, car: Car, member: User, role: str) -> CarMember:
    membership = CarMember(car_id=car.id, user_id=member.id, role=role)
    db.add(membership)
    db.flush()
    return membership


def _shared_world(db: Session, role: str) -> tuple[User, User, Car, Car]:
    """An owner with a car, and a member holding ``role`` on it.

    The member owns a car of their own too, so «their garage» is never
    trivially «the shared car» and ordering has something to say.
    """
    owner = _user(db, "owner@example.com", OWNER_CHAT)
    member = _user(db, "member@example.com", MEMBER_CHAT)
    own_car = _car(db, member, "Skoda", "Octavia", odometer=50000)
    shared_car = _car(db, owner, "Renault", "Megane", odometer=90000)
    _share(db, shared_car, member, role)
    db.commit()
    return owner, member, own_car, shared_car


def _message(text: str | None, chat_id: int) -> Message:
    """A minimally-populated real Message (handlers only touch chat/text)."""
    return Message.model_construct(
        message_id=1,
        date=dt.datetime.now(dt.timezone.utc),
        chat=Chat.model_construct(id=chat_id, type="private"),
        text=text,
        photo=None,
    )


def _callback(data: str, message: Message) -> CallbackQuery:
    return CallbackQuery.model_construct(
        id="cb-1",
        from_user=TelegramUser.model_construct(id=7, is_bot=False, first_name="Тест"),
        chat_instance="chat-instance",
        data=data,
        message=message,
    )


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _log_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(LogEntry)).scalar_one()


# The garage the bot sees


def test_bot_garage_holds_owned_and_shared_cars(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _owner, member, own_car, shared_car = _shared_world(db, "editor")

        cars = service.list_cars(db, member)

        # Owned first only because ids say so — the order is by id, not by
        # ownership, so a shared car never jumps the queue.
        assert [car.id for car in cars] == [own_car.id, shared_car.id]


def test_owner_membership_row_does_not_duplicate_the_owners_car(
    db_session_factory: sessionmaker,
) -> None:
    """The backfilled owner row is a membership too — and must not double the car."""
    with db_session_factory() as db:
        owner = _user(db, "solo@example.com", OWNER_CHAT)
        car = _car(db, owner, "Skoda", "Octavia")
        db.commit()

        assert [c.id for c in service.list_cars(db, owner)] == [car.id]


def test_a_strangers_car_is_invisible_to_the_bot(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        stranger = _user(db, "stranger@example.com", MEMBER_CHAT)
        _car(db, owner, "Renault", "Megane")
        db.commit()

        assert service.list_cars(db, stranger) == []


def test_shared_cars_are_marked_in_the_car_choice_keyboard(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _shared_world(db, "editor")

    asyncio.run(handlers.handle_text(_message("заправка 45л 2500", MEMBER_CHAT)))

    assert _button_texts(replies[0]["reply_markup"]) == [
        "Skoda Octavia",
        "Renault Megane (спільне)",
    ]


def test_status_marks_the_shared_car_for_the_member_but_not_for_the_owner(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        owner, member, _own_car, _shared_car = _shared_world(db, "viewer")

        member_status = service.status_summary(db, member, today=TODAY)
        owner_status = service.status_summary(db, owner, today=TODAY)

    assert "Renault Megane (спільне)" in member_status
    assert "Skoda Octavia (спільне)" not in member_status
    # The owner's own car is never «спільне» to the owner.
    assert "(спільне)" not in owner_status


# Authorship


def test_expense_logged_through_the_bot_carries_its_author(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _owner, member, _own_car, shared_car = _shared_world(db, "editor")
        member_id, shared_id = member.id, shared_car.id

    message = _message("мийка 300", MEMBER_CHAT)
    asyncio.run(handlers.handle_text(message))
    asyncio.run(handlers.cb_expense_car(_callback(f"exp:{shared_id}", message)))
    asyncio.run(handlers.cb_expense_confirm(_callback("expok", message)))

    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == shared_id
        # The editor wrote it — not the car's owner.
        assert log.author_id == member_id


def test_refuel_logged_through_the_bot_carries_its_author(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _owner, member, _own_car, shared_car = _shared_world(db, "editor")
        member_id, shared_id = member.id, shared_car.id

    message = _message("заправка 45л 2500", MEMBER_CHAT)
    asyncio.run(handlers.handle_text(message))
    asyncio.run(handlers.cb_refuel_car(_callback(f"ref:{shared_id}", message)))
    asyncio.run(handlers.cb_refuel_confirm(_callback("refok", message)))

    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == shared_id
        assert log.author_id == member_id


def test_service_writers_accept_an_author(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        _owner, member, own_car, _shared = _shared_world(db, "editor")

        with_author = service.create_quick_expense(
            db, own_car.id, "мийка", 300, author_id=member.id
        )
        anonymous = service.create_quick_expense(db, own_car.id, "паркінг", 50)

        assert with_author.author_id == member.id
        assert anonymous.author_id is None


def test_interval_completion_from_a_reminder_carries_its_author(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        car = _car(db, owner, "Skoda", "Octavia")
        interval = ServiceInterval(
            car_id=car.id, title="Олива двигуна", interval_km=10000, last_odometer=39000
        )
        db.add(interval)
        db.commit()

        completion = service.complete_interval_now(db, interval, author_id=owner.id)

        assert completion.log.author_id == owner.id


# A viewer may look, not write


def test_viewer_with_only_a_shared_car_is_refused_politely(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    """No car of their own, view-only on the shared one: nothing to write to."""
    with bot_db() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        viewer = _user(db, "viewer@example.com", MEMBER_CHAT)
        car = _car(db, owner, "Renault", "Megane")
        _share(db, car, viewer, "viewer")
        db.commit()

    asyncio.run(handlers.handle_text(_message("мийка 300", MEMBER_CHAT)))

    assert replies[0]["text"] == handlers.VIEW_ONLY_TEXT
    # Refused, not merely «no cars»: the viewer can plainly see the car.
    assert replies[0]["text"] != handlers.NO_CARS_TEXT
    assert "лише для перегляду" in replies[0]["text"]
    with bot_db() as db:
        assert _log_count(db) == 0


def test_viewer_car_is_absent_from_the_write_keyboard(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    """A car you cannot write to is not offered as a target."""
    with bot_db() as db:
        _shared_world(db, "viewer")

    asyncio.run(handlers.handle_text(_message("заправка 45л 2500", MEMBER_CHAT)))

    # Only their own car remains -> single car, straight to confirmation.
    assert replies[0]["reply_markup"] is not None
    assert _button_texts(replies[0]["reply_markup"]) == ["Зберегти", "Скасувати"]
    assert "Skoda Octavia" in replies[0]["text"]
    assert "Renault Megane" not in replies[0]["text"]


@pytest.mark.parametrize(
    ("callback_data", "pending_setter"),
    [
        ("exp:{car_id}", "expense"),
        ("ref:{car_id}", "refuel"),
    ],
)
def test_viewer_cannot_reach_a_shared_car_with_a_crafted_callback(
    bot_db: sessionmaker,
    replies: list[dict],
    callback_data: str,
    pending_setter: str,
) -> None:
    with bot_db() as db:
        _owner, _member, _own_car, shared_car = _shared_world(db, "viewer")
        shared_id = shared_car.id

    message = _message(None, MEMBER_CHAT)
    if pending_setter == "expense":
        handlers._pending_expenses[MEMBER_CHAT] = handlers.PendingExpense(
            title="мийка", amount=300
        )
        handler = handlers.cb_expense_car
    else:
        handlers._pending_refuels[MEMBER_CHAT] = handlers.PendingRefuel(
            liters=45, price_per_liter=55.56, total_cost=2500, date=TODAY
        )
        handler = handlers.cb_refuel_car

    try:
        asyncio.run(handler(_callback(callback_data.format(car_id=shared_id), message)))
    finally:
        handlers._pending_expenses.pop(MEMBER_CHAT, None)
        handlers._pending_refuels.pop(MEMBER_CHAT, None)

    assert any(reply.get("text") == handlers.VIEW_ONLY_TEXT for reply in replies)
    with bot_db() as db:
        assert _log_count(db) == 0


def test_viewer_cannot_write_by_confirming_a_stale_pending_entry(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _owner, _member, _own_car, shared_car = _shared_world(db, "viewer")
        shared_id = shared_car.id

    message = _message(None, MEMBER_CHAT)
    handlers._pending_expenses[MEMBER_CHAT] = handlers.PendingExpense(
        title="мийка", amount=300, car_id=shared_id
    )
    try:
        asyncio.run(handlers.cb_expense_confirm(_callback("expok", message)))
    finally:
        handlers._pending_expenses.pop(MEMBER_CHAT, None)

    assert any(reply.get("text") == handlers.VIEW_ONLY_TEXT for reply in replies)
    with bot_db() as db:
        assert _log_count(db) == 0


def test_viewer_cannot_move_the_odometer_of_a_shared_car(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _owner, _member, _own_car, shared_car = _shared_world(db, "viewer")
        shared_id = shared_car.id

    message = _message("123456", MEMBER_CHAT)
    asyncio.run(handlers.cb_odometer(_callback(f"odo:{shared_id}:123456", message)))

    assert any(reply.get("text") == handlers.VIEW_ONLY_TEXT for reply in replies)
    with bot_db() as db:
        assert db.get(Car, shared_id).current_odometer == 90000  # untouched


def test_editor_may_move_the_odometer_of_a_shared_car(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _owner, _member, _own_car, shared_car = _shared_world(db, "editor")
        shared_id = shared_car.id

    message = _message("123456", MEMBER_CHAT)
    asyncio.run(handlers.cb_odometer(_callback(f"odo:{shared_id}:123456", message)))

    with bot_db() as db:
        assert db.get(Car, shared_id).current_odometer == 123456


def test_viewer_may_still_read_status_and_ask_for_a_report(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    """Refusing writes must not lock a viewer out of what they came for."""
    with bot_db() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        viewer = _user(db, "viewer@example.com", MEMBER_CHAT)
        car = _car(db, owner, "Renault", "Megane")
        _share(db, car, viewer, "viewer")
        db.commit()

    asyncio.run(handlers.cmd_status(_message("/status", MEMBER_CHAT)))
    assert "Renault Megane (спільне)" in replies[0]["text"]

    asyncio.run(handlers.cmd_report(_message("/report", MEMBER_CHAT)))
    assert replies[1]["document"].data.startswith(b"%PDF")


# Reminders: the owner, and only the owner


def _overdue(db: Session, car: Car) -> ServiceInterval:
    interval = ServiceInterval(
        car_id=car.id,
        title="Олива двигуна",
        interval_km=10000,
        last_odometer=car.current_odometer - 11000,
    )
    db.add(interval)
    db.flush()
    return interval


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_service_reminders_reach_the_owner_only(
    db_session_factory: sessionmaker, role: str
) -> None:
    """A deliberate anti-spam rule: one due interval, one message.

    The member is linked to Telegram and has real access to the car — they
    are simply not the person the reminder is for.
    """
    with db_session_factory() as db:
        owner = _user(db, "owner@example.com", OWNER_CHAT)
        member = _user(db, "member@example.com", MEMBER_CHAT)
        car = _car(db, owner, "Renault", "Megane", odometer=90000)
        _share(db, car, member, role)
        interval = _overdue(db, car)
        db.commit()
        owner_id, interval_id = owner.id, interval.id

        targets = service.reminder_targets(db, today=TODAY)

        assert [user.id for user, _items in targets] == [owner_id]
        assert [item.interval.id for item in targets[0][1]] == [interval_id]


def test_a_member_still_gets_reminders_about_their_own_car(
    db_session_factory: sessionmaker,
) -> None:
    """Owner-only is about *this* car, not about muting the member entirely."""
    with db_session_factory() as db:
        owner, member, own_car, shared_car = _shared_world(db, "editor")
        _overdue(db, own_car)
        _overdue(db, shared_car)
        db.commit()
        owner_id, member_id, own_car_id, shared_car_id = (
            owner.id,
            member.id,
            own_car.id,
            shared_car.id,
        )

        targets = service.reminder_targets(db, today=TODAY)

        by_user = {user.id: [item.car.id for item in items] for user, items in targets}
        assert by_user == {owner_id: [shared_car_id], member_id: [own_car_id]}
