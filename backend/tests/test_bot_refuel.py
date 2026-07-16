"""Bot photo and refuel flows: message parsing, confirm-before-save, and
telling a fuel receipt from a service order.

The OCR binary is never involved: extract_text is monkeypatched in ocr_llm,
so these tests describe the bot's behaviour, not tesseract's.
"""

import asyncio
import datetime as dt
from pathlib import Path

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.bot import handlers, service
from app.bot.parsers import parse_refuel
from app.config import settings
from app.models import Car, LogEntry, LogPhoto, MaintenanceDetails, RefuelDetails, User

CHAT_ID = 42
TODAY = dt.date.today()
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"


# Parser cases (the shapes the bot promises to understand)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "заправка 45л 2500",
            {"liters": 45.0, "price_per_liter": 55.56, "total_cost": 2500.0},
        ),
        (
            "заправка 2500 45.5 л",
            {"liters": 45.5, "price_per_liter": 54.95, "total_cost": 2500.0},
        ),
        (
            "заправка 45л 55.99 грн/л",
            {"liters": 45.0, "price_per_liter": 55.99, "total_cost": 2519.55},
        ),
    ],
)
def test_parse_refuel_examples(text: str, expected: dict) -> None:
    assert parse_refuel(text) == expected


def test_parse_refuel_needs_the_leading_word() -> None:
    assert parse_refuel("45л 2500") is None


# Fixtures: a linked user with one car, captured replies, patched storage


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(target))
    return target


@pytest.fixture()
def bot_db(
    db_session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> sessionmaker:
    monkeypatch.setattr(handlers, "SessionLocal", db_session_factory)
    return db_session_factory


@pytest.fixture()
def replies(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []

    async def fake_answer(self, text: str = "", **kwargs):
        entry = {"text": text, "reply_markup": kwargs.get("reply_markup")}
        sent.append(entry)
        # Telegram answers with the message it sent, and the progress loader
        # edits that one in place rather than sending a second: the fake has to
        # do the same, or a test would count messages the user never sees.
        return _SentMessage(entry)

    async def fake_answer_document(self, document, **kwargs) -> None:
        sent.append({"document": document, "caption": kwargs.get("caption")})

    async def fake_callback_answer(self, text: str | None = None, **kwargs) -> None:
        sent.append({"callback_answer": text})

    monkeypatch.setattr(Message, "answer", fake_answer)
    monkeypatch.setattr(Message, "answer_document", fake_answer_document)
    monkeypatch.setattr(CallbackQuery, "answer", fake_callback_answer)
    return sent


def _seed_user_with_car(db: Session, odometer: int = 50000) -> tuple[User, Car]:
    user = User(
        email="refueler@example.com", hashed_password="x", telegram_chat_id=str(CHAT_ID)
    )
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


class _SentMessage:
    """What Message.answer returns: a handle whose edits rewrite the entry."""

    def __init__(self, entry: dict) -> None:
        self._entry = entry

    async def edit_text(self, text: str, **kwargs) -> None:
        self._entry["text"] = text
        if "reply_markup" in kwargs:
            self._entry["reply_markup"] = kwargs["reply_markup"]


def _message(text: str | None = None, photo: bool = False) -> Message:
    """A minimally-populated real Message (handlers only touch chat/text)."""
    return Message.model_construct(
        message_id=1,
        date=dt.datetime.now(dt.timezone.utc),
        chat=Chat.model_construct(id=CHAT_ID, type="private"),
        text=text,
        photo=[_PhotoSize()] if photo else None,
    )


class _PhotoSize:
    """Stand-in for the largest PhotoSize; only its identity is used."""

    file_id = "file-123"


def _callback(data: str, message: Message) -> CallbackQuery:
    return CallbackQuery.model_construct(
        id="cb-1",
        from_user=TelegramUser.model_construct(id=7, is_bot=False, first_name="Тест"),
        chat_instance="chat-instance",
        data=data,
        message=message,
    )


class _FakeBot:

    def __init__(self, image_bytes: bytes = JPEG_BYTES) -> None:
        self.image_bytes = image_bytes
        self.downloaded: list[object] = []

    async def download(self, file, destination) -> None:
        self.downloaded.append(file)
        destination.write(self.image_bytes)


def _button_texts(reply_markup) -> list[str]:
    return [
        button.text for row in reply_markup.inline_keyboard for button in row
    ]


def _callback_data(reply_markup) -> list[str]:
    return [
        button.callback_data for row in reply_markup.inline_keyboard for button in row
    ]


def _refuel_count(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(LogEntry).where(LogEntry.type == "refuel")
    ).scalar_one()


# Text refuel: confirm before save


def test_refuel_text_asks_for_confirmation_without_writing(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    asyncio.run(handlers.handle_text(_message("заправка 45л 2500")))

    assert len(replies) == 1
    assert _button_texts(replies[0]["reply_markup"]) == ["Зберегти", "Скасувати"]
    with bot_db() as db:
        assert _refuel_count(db) == 0  # nothing saved yet


def test_refuel_confirm_then_create_writes_exactly_one_log(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _user, car = _seed_user_with_car(db)
        car_id = car.id

    message = _message("заправка 45л 2500")
    asyncio.run(handlers.handle_text(message))
    with bot_db() as db:
        assert _refuel_count(db) == 0

    asyncio.run(handlers.cb_refuel_confirm(_callback("refok", message)))

    with bot_db() as db:
        assert _refuel_count(db) == 1
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == car_id
        assert log.type == "refuel"
        assert log.odometer == 50000  # the car's current reading
        assert log.date == TODAY
        assert float(log.total_cost) == 2500.0
        detail = db.get(RefuelDetails, log.id)
        assert float(detail.liters) == 45.0
        assert float(detail.price_per_liter) == 55.56
        assert detail.is_full_tank is True

    # A second confirm tap must not duplicate the log: the pending refuel is
    # consumed by the first one.
    asyncio.run(handlers.cb_refuel_confirm(_callback("refok", message)))
    with bot_db() as db:
        assert _refuel_count(db) == 1


def test_refuel_cancel_writes_nothing(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    message = _message("заправка 45л 2500")
    asyncio.run(handlers.handle_text(message))
    asyncio.run(handlers.cb_refuel_cancel(_callback("refno", message)))

    with bot_db() as db:
        assert _refuel_count(db) == 0


def test_quick_expense_also_confirms_before_saving(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    message = _message("мийка 300")
    asyncio.run(handlers.handle_text(message))

    assert _button_texts(replies[-1]["reply_markup"]) == ["Зберегти", "Скасувати"]
    with bot_db() as db:
        assert db.execute(select(func.count()).select_from(LogEntry)).scalar_one() == 0

    asyncio.run(handlers.cb_expense_confirm(_callback("expok", message)))
    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.type == "expense"
        assert log.notes == "мийка"
        assert float(log.total_cost) == 300.0


def test_refuel_with_two_cars_asks_which_car_first(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        user, _car = _seed_user_with_car(db)
        second = Car(
            user_id=user.id,
            brand="Renault",
            model="Megane",
            year=2016,
            fuel_type="petrol",
            current_odometer=90000,
        )
        db.add(second)
        db.commit()
        second_id = second.id

    message = _message("заправка 45л 2500")
    asyncio.run(handlers.handle_text(message))
    assert _button_texts(replies[0]["reply_markup"]) == [
        "Skoda Octavia",
        "Renault Megane",
    ]
    with bot_db() as db:
        assert _refuel_count(db) == 0

    # Pick the second car -> confirmation, still nothing written.
    asyncio.run(handlers.cb_refuel_car(_callback(f"ref:{second_id}", message)))
    assert _button_texts(replies[1]["reply_markup"]) == ["Зберегти", "Скасувати"]
    with bot_db() as db:
        assert _refuel_count(db) == 0

    asyncio.run(handlers.cb_refuel_confirm(_callback("refok", message)))
    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == second_id
        assert log.odometer == 90000


# Photo receipts


def test_photo_flow_creates_log_and_photo_row(
    bot_db: sessionmaker,
    replies: list[dict],
    uploads_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with bot_db() as db:
        _user, car = _seed_user_with_car(db)
        car_id, user_id = car.id, car.user_id

    # The bot reads receipts through the shared entry point now, so the mock
    # goes where the API's does: one reader, one place to patch.
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes: "ОККО\nПАЛЬНЕ А-95\n45.00 Л\nЦІНА 55.99\nДО СПЛАТИ 2519.55",
    )

    message = _message(photo=True)
    asyncio.run(handlers.handle_photo(message, _FakeBot()))

    # Recognized values are shown for confirmation, nothing is written yet.
    assert "45" in replies[0]["text"]
    assert _button_texts(replies[0]["reply_markup"]) == ["Зберегти", "Скасувати"]
    with bot_db() as db:
        assert _refuel_count(db) == 0

    asyncio.run(handlers.cb_refuel_confirm(_callback("refok", message)))

    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == car_id
        assert log.type == "refuel"
        detail = db.get(RefuelDetails, log.id)
        assert float(detail.liters) == 45.0
        assert float(detail.price_per_liter) == 55.99
        assert detail.gas_station == "OKKO"

        photo = db.execute(select(LogPhoto)).scalar_one()
        assert photo.log_entry_id == log.id
        assert photo.content_type == "image/jpeg"
        assert photo.size == len(JPEG_BYTES)
        stored = uploads_dir / str(user_id) / photo.filename
        assert stored.is_file()
        assert stored.read_bytes() == JPEG_BYTES


def test_photo_flow_reports_missing_tesseract_in_ukrainian(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytesseract

    with bot_db() as db:
        _seed_user_with_car(db)

    def _no_binary(image_bytes: bytes) -> str:
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
_no_binary)

    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert len(replies) == 1
    assert replies[0]["reply_markup"] is None
    assert "розпізна" in replies[0]["text"].lower()
    with bot_db() as db:
        assert _refuel_count(db) == 0


def test_photo_flow_without_recognized_values_asks_for_text(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
lambda image_bytes: "розмитий чек")

    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert replies[0]["reply_markup"] is None
    with bot_db() as db:
        assert _refuel_count(db) == 0


def test_photo_flow_requires_a_linked_account(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bytes] = []
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
lambda image: called.append(image))

    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert "прив'яза" in replies[0]["text"].lower()
    assert called == []  # no OCR work for strangers


# Photo service orders (the same photo handler, a different piece of paper)


ALEX_SO_ORDER = """ТОВ "АЛЕКС СО"
Наряд-замовлення №А000033003 від 03.12.2022
1  Олива моторна 5W-30 5л      1      2255,00  2255,00
2  Фільтр масляний ЦБ012317    1       566,00   566,00
Запчастини та матеріали:            7542,00
Роботи:                              681,38
Разом до сплати:                    8223,38
"""


def test_a_photographed_order_becomes_a_service_entry(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    with bot_db() as db:
        _user, car = _seed_user_with_car(db)
        car_id = car.id

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO_ORDER
    )

    message = _message(photo=True)
    asyncio.run(handlers.handle_photo(message, _FakeBot()))

    # Read back for confirmation, written only on «Зберегти» — same promise as
    # a receipt.
    assert "8223.38" in replies[0]["text"]
    assert _button_texts(replies[0]["reply_markup"]) == ["Зберегти", "Скасувати"]
    with bot_db() as db:
        assert db.execute(select(func.count(LogEntry.id))).scalar_one() == 0

    asyncio.run(handlers.cb_maintenance_confirm(_callback("mntok", message)))

    with bot_db() as db:
        log = db.execute(select(LogEntry)).scalar_one()
        assert log.car_id == car_id
        assert log.type == "maintenance"
        assert log.date == dt.date(2022, 12, 3)
        assert log.odometer == 50000  # the car's current reading
        detail = db.get(MaintenanceDetails, log.id)
        assert float(detail.parts_cost) == 7542.00
        assert float(detail.labor_cost) == 681.38
        assert "Олива моторна 5W-30 5л" in detail.items


def test_an_order_photo_is_never_filed_as_a_refuel(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Олива моторна 5W-30 5л» hands the receipt parser five litres and the
    bill to divide by them. Nothing about that is a refuel."""
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO_ORDER
    )
    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert _callback_data(replies[0]["reply_markup"]) == ["mntok", "mntno"]
    assert "заправ" not in replies[0]["text"].lower()


def test_a_receipt_is_still_a_receipt(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same guard: teaching the bot to see orders must
    not cost it the receipts it already read."""
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes: "ОККО\nПАЛЬНЕ А-95\n45.00 Л\nЦІНА 55.99\nДО СПЛАТИ 2519.55",
    )
    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert _callback_data(replies[0]["reply_markup"]) == ["refok", "refno"]


def test_a_cancelled_order_writes_nothing(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO_ORDER
    )
    message = _message(photo=True)
    asyncio.run(handlers.handle_photo(message, _FakeBot()))
    asyncio.run(handlers.cb_maintenance_cancel(_callback("mntno", message)))

    with bot_db() as db:
        assert db.execute(select(func.count(LogEntry.id))).scalar_one() == 0


def test_an_order_confirmed_twice_is_saved_once(
    bot_db: sessionmaker, replies: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A double tap on «Зберегти» is a slow connection, not a second service."""
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO_ORDER
    )
    message = _message(photo=True)
    asyncio.run(handlers.handle_photo(message, _FakeBot()))
    asyncio.run(handlers.cb_maintenance_confirm(_callback("mntok", message)))
    asyncio.run(handlers.cb_maintenance_confirm(_callback("mntok", message)))

    with bot_db() as db:
        assert db.execute(select(func.count(LogEntry.id))).scalar_one() == 1


# Handler wiring


def test_commands_are_registered_before_the_catch_all_text_handler() -> None:
    """aiogram matches in registration order: F.text would swallow /report."""
    registered = [
        handler.callback.__name__ for handler in handlers.router.message.handlers
    ]
    catch_all = registered.index("handle_text")
    for name in ("cmd_start", "cmd_help", "cmd_status", "cmd_report"):
        assert registered.index(name) < catch_all, name
    # Only the unfiltered fallback may come after the text router.
    assert registered[catch_all + 1 :] == ["handle_unknown"]


def test_fallback_handler_is_last_and_takes_anything() -> None:
    """A sticker, a voice note or a location used to get silence."""
    last = handlers.router.message.handlers[-1]
    assert last.callback.__name__ == "handle_unknown"
    assert not last.filters  # unfiltered: whatever the others left behind


def test_fallback_handler_explains_what_the_bot_understands(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    # A voice note: no text, no photo, no parser will ever match it.
    asyncio.run(handlers.handle_unknown(_message()))

    assert len(replies) == 1
    assert replies[0]["text"] == handlers.UNKNOWN_TEXT


def test_report_command_sends_a_pdf_document(
    bot_db: sessionmaker, replies: list[dict]
) -> None:
    with bot_db() as db:
        _seed_user_with_car(db)

    asyncio.run(handlers.cmd_report(_message("/report")))

    document = replies[0]["document"]
    assert document.filename.endswith(".pdf")
    assert document.data.startswith(b"%PDF")
    assert "Skoda Octavia" in replies[0]["caption"]


# Service level


def test_create_refuel_uses_car_odometer_and_full_tank(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car = _seed_user_with_car(db, odometer=123456)
        log = service.create_refuel(
            db,
            car.id,
            liters=40.0,
            price_per_liter=55.0,
            total_cost=2200.0,
        )
        assert log is not None
        assert log.odometer == 123456
        assert log.date == TODAY
        assert log.refuel.is_full_tank is True
        assert _refuel_count(db) == 1


def test_failed_commit_leaves_no_photo_orphaned_on_disk(
    db_session_factory: sessionmaker,
    uploads_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The photo is written only once the transaction it belongs to lands."""
    with db_session_factory() as db:
        _user, car = _seed_user_with_car(db)
        car_id, user_id = car.id, car.user_id

    def _boom(self) -> None:
        raise RuntimeError("database went away mid-commit")

    monkeypatch.setattr(Session, "commit", _boom)

    with pytest.raises(RuntimeError):
        service.create_refuel(
            db_session_factory(),
            car_id,
            liters=45.0,
            price_per_liter=55.0,
            total_cost=2475.0,
            photo=service.RefuelPhoto(image_bytes=JPEG_BYTES),
        )

    user_dir = uploads_dir / str(user_id)
    orphans = list(user_dir.iterdir()) if user_dir.is_dir() else []
    assert orphans == []


def test_create_refuel_unknown_car_returns_none(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        assert (
            service.create_refuel(
                db, 999, liters=40.0, price_per_liter=55.0, total_cost=2200.0
            )
            is None
        )


def test_recognize_refuel_translates_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytesseract

    def _no_binary(image_bytes: bytes) -> str:
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
_no_binary)
    with pytest.raises(service.OcrUnavailableError):
        service.recognize_refuel(JPEG_BYTES)


def test_photo_progress_becomes_the_result_in_one_message(
    bot_db: sessionmaker,
    replies: list[dict],
    uploads_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The «Розпізнаю чек» line turns into the answer, it does not pile up."""
    with bot_db() as db:
        _seed_user_with_car(db)

    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes: "ОККО\nПАЛЬНЕ А-95\n45.00 Л\nЦІНА 55.99\nДО СПЛАТИ 2519.55",
    )

    asyncio.run(handlers.handle_photo(_message(photo=True), _FakeBot()))

    assert len(replies) == 1
    assert "Розпізнаю чек" not in replies[0]["text"]
    assert "45.00 л" in replies[0]["text"]
    assert replies[0]["reply_markup"] is not None
