"""Aiogram v3 handlers: linking, /status, odometer, expenses, refuels, /report."""

from __future__ import annotations

import asyncio
import datetime as dt
import time
import io
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Message,
)
from sqlalchemy.orm import Session

from app.bot import service
from app.bot.parsers import (
    parse_bare_odometer,
    parse_odometer,
    parse_quick_expense,
    parse_refuel,
)
from app.database import SessionLocal
from app.models import User
from app.routers.telegram import InvalidLinkCodeError

router = Router()


@dataclass
class PendingExpense:

    title: str
    amount: float
    car_id: Optional[int] = None


@dataclass
class PendingRefuel:

    liters: float
    price_per_liter: float
    total_cost: float
    date: dt.date
    gas_station: Optional[str] = None
    photo: Optional[service.RefuelPhoto] = None
    car_id: Optional[int] = None


@dataclass
class PendingMaintenance:

    items: list[str]
    parts_cost: float
    labor_cost: float
    total_cost: float
    date: dt.date
    car_id: Optional[int] = None


# What the bot last asked this chat for. A bare number means nothing on its
# own, but everything right after «надішліть пробіг» — so the question is
# remembered, briefly, and only for that.
_ASK_TTL_SECONDS = 10 * 60
_awaiting_odometer: dict[int, float] = {}

_pending_expenses: dict[int, PendingExpense] = {}
_pending_refuels: dict[int, PendingRefuel] = {}
_pending_maintenance: dict[int, PendingMaintenance] = {}

SAVE_BUTTON = "Зберегти"
CANCEL_BUTTON = "Скасувати"

LINK_HINT = (
    "Щоб прив'язати акаунт, відкрийте веб-додаток Kapot Tracker, розділ «Гараж», "
    "згенеруйте код і надішліть його сюди командою:\n/start <код>"
)

NOT_LINKED_TEXT = "Ваш Telegram ще не прив'язано до акаунта Kapot Tracker.\n\n" + LINK_HINT

# Persistent keys under the input field. Commands still work, but nothing has
# to be remembered or typed: the two everyday actions sit one tap away and the
# rest hide behind a menu so the keyboard stays two rows tall.
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="⛽ Заправка"),
            KeyboardButton(text="🛣 Пробіг"),
            KeyboardButton(text="💸 Витрата"),
        ],
        [
            KeyboardButton(text="📊 Стан"),
            KeyboardButton(text="📄 Звіт"),
            KeyboardButton(text="❓ Довідка"),
        ],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

ASK_ODOMETER = "Надішліть поточний пробіг — просто числом, напр. 240054."
ASK_REFUEL = "Надішліть заправку: «заправка 45л 2500» або фото чека."
ASK_EXPENSE = "Надішліть витрату: «мийка 300»."

HELP_TEXT = (
    "Доступні команди:\n"
    "/start <код> — прив'язати акаунт Kapot Tracker\n"
    "/status — стан авто та найближчі ТО\n"
    "/report — PDF-звіт по авто\n"
    "/digest on|off — тижневий підсумок у неділю\n"
    "/help — ця довідка\n\n"
    "Також можна просто надіслати:\n"
    "- «пробіг 240054» — оновити пробіг;\n"
    "- «мийка 300» — швидка витрата;\n"
    "- «заправка 45л 2500» — запис про заправку;\n"
    "- фото чека — розпізнаю заправку автоматично."
)

UNKNOWN_TEXT = (
    "Не зрозумів повідомлення. Ось що я вмію:\n"
    "- «пробіг 240054» — оновити пробіг;\n"
    "- «мийка 300» — швидка витрата;\n"
    "- «заправка 45л 2500» — запис про заправку;\n"
    "- фото чека — розпізнаю заправку автоматично;\n"
    "- /status — стан авто та найближчі ТО;\n"
    "- /report — PDF-звіт по авто;\n"
    "- /help — довідка."
)

NO_CARS_TEXT = "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."

# A viewer is not doing anything wrong — they were invited, they just were not
# given the pen. The refusal says who can change that, so it ends the matter
# instead of leaving them wondering whether the bot is broken.
VIEW_ONLY_TEXT = (
    "До цього авто у вас доступ лише для перегляду, тому я не можу зберегти "
    "запис. Стан авто і найближчі ТО завжди можна подивитися: /status.\n\n"
    "Якщо потрібно вести записи — попросіть власника авто змінити вашу роль "
    "на «Редактор» у веб-додатку Kapot Tracker."
)

CANCELLED_TEXT = "Скасовано. Нічого не збережено."

EXPIRED_TEXT = "Запис застарів. Надішліть його ще раз."

DIGEST_ON_TEXT = (
    "Тижневий дайджест увімкнено. Щонеділі надсилатиму підсумок тижня по "
    "кожному авто — витрати, пробіг, розхід і найближче ТО. За тиждень без "
    "записів дайджесту не буде."
)

DIGEST_OFF_TEXT = "Тижневий дайджест вимкнено. Увімкнути назад: /digest on"

# The bare «/digest» is a question, not a command: it answers with the state
# and how to change it, and toggles nothing. Guessing that a user who typed
# «/digest» meant «switch it» is how a setting gets flipped by accident.
DIGEST_STATE_TEMPLATE = (
    "Тижневий дайджест: {state}.\nЗмінити: /digest on або /digest off"
)

OCR_UNAVAILABLE_TEXT = (
    "Не вдалося розпізнати чек: на сервері не встановлено tesseract. "
    "Надішліть заправку текстом, наприклад: заправка 45л 2500"
)

OCR_FAILED_TEXT = (
    "Не вдалося розпізнати дані на фото. Спробуйте зняти чек рівніше і "
    "при кращому світлі або надішліть заправку текстом, наприклад: "
    "заправка 45л 2500"
)


def _car_label(car, user: Optional[User] = None) -> str:
    return service.car_label(car, user)


async def _refuse_write(message: Message, db: Session, user: User) -> None:
    """Explain why there is nothing to write to: no cars at all, or view-only.

    Both answers are true and neither leaks: a user with no access to a car
    never reaches this at all — they are told «Авто не знайдено», the same
    thing they hear about a car that does not exist.
    """
    if service.list_cars(db, user):
        await message.answer(VIEW_ONLY_TEXT)
    else:
        await message.answer(NO_CARS_TEXT)


def _confirm_keyboard(confirm_data: str, cancel_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=SAVE_BUTTON, callback_data=confirm_data),
                InlineKeyboardButton(text=CANCEL_BUTTON, callback_data=cancel_data),
            ]
        ]
    )


def _car_choice_keyboard(
    cars: list, prefix: str, user: Optional[User] = None
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_car_label(car, user), callback_data=f"{prefix}:{car.id}"
                )
            ]
            for car in cars
        ]
    )


class _Progress:
    """A single message that animates while work happens, then becomes the result.

    Recognising a receipt can take the best part of a minute once the vision
    fallback is involved, and silence for that long reads as a dead bot. The
    dots live in one message that is edited in place: a new message per frame
    would bury the chat.
    """

    FRAMES = ("", ".", "..", "...")

    def __init__(self, message: Message, text: str) -> None:
        self._message = message
        self._text = text
        self._sent: Message | None = None
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> "_Progress":
        sent = await self._message.answer(self._text)
        # No handle on the sent message (an old Bot API, a stub) means no
        # animation — but the work and its result must go on regardless.
        if hasattr(sent, "edit_text"):
            self._sent = sent
            self._task = asyncio.create_task(self._animate())
        return self

    async def _animate(self) -> None:
        frame = 0
        while True:
            await asyncio.sleep(0.7)
            frame = (frame + 1) % len(self.FRAMES)
            try:
                await self._sent.edit_text(f"{self._text}{self.FRAMES[frame]}")
            except TelegramBadRequest:
                # Telegram rejects an edit to identical text; nothing to do.
                pass
            except Exception:
                return

    async def finish(self, text: str, **kwargs) -> None:
        """Replace the animation with the result, in the same message."""
        self._stop()
        if self._sent is None:
            await self._message.answer(text, **kwargs)
            return
        try:
            await self._sent.edit_text(text, **kwargs)
        except Exception:
            await self._message.answer(text, **kwargs)

    def _stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def __aexit__(self, *exc_info) -> None:
        self._stop()


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    """Link the chat when a code is supplied, otherwise explain how to."""
    code = (command.args or "").strip()
    if not code:
        await message.answer(LINK_HINT)
        return
    with SessionLocal() as db:
        try:
            user = service.link_user_by_code(db, code, str(message.chat.id))
        except InvalidLinkCodeError:
            await message.answer(
                "Код недійсний або прострочений. Згенеруйте новий у веб-додатку "
                "Kapot Tracker (розділ «Гараж») і надішліть /start <код> ще раз."
            )
            return
        cars = service.list_cars(db, user)
        if cars:
            car_lines = "\n".join(
                f"- {_car_label(car, user)}, {car.current_odometer} км" for car in cars
            )
            await message.answer(
                "Акаунт прив'язано! Ваші авто:\n"
                f"{car_lines}\n\n"
                "Користуйтеся кнопками нижче або надішліть /help.",
                reply_markup=MAIN_KEYBOARD,
            )
        else:
            await message.answer(
                "Акаунт прив'язано! У гаражі поки немає авто — додайте перше "
                "у веб-додатку Kapot Tracker.",
                reply_markup=MAIN_KEYBOARD,
            )


@router.message(F.text == "⛽ Заправка")
async def key_refuel(message: Message) -> None:
    await message.answer(ASK_REFUEL)


@router.message(F.text == "🛣 Пробіг")
async def key_odometer(message: Message) -> None:
    _awaiting_odometer[message.chat.id] = time.monotonic()
    await message.answer(ASK_ODOMETER)


@router.message(F.text == "📊 Стан")
async def key_status(message: Message) -> None:
    await cmd_status(message)


@router.message(F.text == "💸 Витрата")
async def key_expense(message: Message) -> None:
    await message.answer(ASK_EXPENSE)


@router.message(F.text == "📄 Звіт")
async def key_report(message: Message) -> None:
    await cmd_report(message)


@router.message(F.text == "❓ Довідка")
async def key_help(message: Message) -> None:
    await cmd_help(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=MAIN_KEYBOARD)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return
        await message.answer(service.status_summary(db, user), reply_markup=MAIN_KEYBOARD)


@router.message(Command("digest"))
async def cmd_digest(message: Message, command: CommandObject) -> None:
    argument = (command.args or "").strip().lower()
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return
        if argument in ("on", "off"):
            enabled = argument == "on"
            service.set_digest_enabled(db, user, enabled)
            await message.answer(DIGEST_ON_TEXT if enabled else DIGEST_OFF_TEXT)
            return
        state = "увімкнено" if user.digest_enabled else "вимкнено"
        await message.answer(DIGEST_STATE_TEMPLATE.format(state=state))


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return
        # Checked before the download and the OCR: a viewer's photo can never
        # become a log entry, so there is nothing to spend tesseract on.
        if not service.list_writable_cars(db, user):
            await _refuse_write(message, db, user)
            return

        buffer = io.BytesIO()
        # The last PhotoSize is the largest one Telegram kept.
        await bot.download(message.photo[-1], destination=buffer)
        image_bytes = buffer.getvalue()

        async with _Progress(message, "Розпізнаю фото") as progress:
            try:
                # OCR is CPU-bound and slow: keep the event loop free for other
                # chats while tesseract works.
                reading = await asyncio.to_thread(service.recognize_photo, image_bytes)
            except service.OcrUnavailableError:
                await progress.finish(OCR_UNAVAILABLE_TEXT)
                return

            if reading.kind == "work_order":
                order = reading.work_order
                await _handle_maintenance(
                    message,
                    db,
                    user,
                    PendingMaintenance(
                        items=order.items,
                        parts_cost=order.parts_cost or 0.0,
                        labor_cost=order.labor_cost or 0.0,
                        total_cost=order.total_cost or 0.0,
                        date=_parsed_date(order.date),
                    ),
                    progress,
                )
                return

            parsed = reading.receipt
            if not parsed.liters or not parsed.total_cost or not parsed.price_per_liter:
                # Partial beats nothing: a total alone still saves typing, and
                # the alternative is the user retyping a receipt we half read.
                if parsed.total_cost:
                    await progress.finish(
                        f"Прочитав лише суму: {parsed.total_cost:.2f} грн.\n"
                        "Надішліть заправку текстом, напр.: "
                        f"заправка 45л {parsed.total_cost:.0f}"
                    )
                    return
                await progress.finish(OCR_FAILED_TEXT)
                return

            await _handle_refuel(
                message,
                db,
                user,
                PendingRefuel(
                    liters=parsed.liters,
                    price_per_liter=parsed.price_per_liter,
                    total_cost=parsed.total_cost,
                    date=parsed.date or dt.date.today(),
                    gas_station=parsed.gas_station,
                    photo=service.RefuelPhoto(image_bytes=image_bytes),
                ),
                progress,
            )


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return
        cars = service.list_cars(db, user)
        if not cars:
            await message.answer(NO_CARS_TEXT)
            return
        if len(cars) == 1:
            await _send_report(message, db, cars[0], user)
            return
        await message.answer(
            "Для якого авто підготувати звіт?",
            reply_markup=_car_choice_keyboard(cars, "rep", user),
        )


async def _send_report(
    message: Message, db: Session, car, user: Optional[User] = None
) -> None:
    pdf_bytes = await asyncio.to_thread(service.build_report, db, car)
    document = BufferedInputFile(
        pdf_bytes, filename=f"kapot-tracker-report-{car.id}.pdf"
    )
    await message.answer_document(document, caption=f"Звіт: {_car_label(car, user)}")

def _was_asked_for_odometer(chat_id: int) -> bool:
    asked_at = _awaiting_odometer.get(chat_id)
    if asked_at is None:
        return False
    if time.monotonic() - asked_at > _ASK_TTL_SECONDS:
        _awaiting_odometer.pop(chat_id, None)
        return False
    return True


@router.message(F.text)
async def handle_text(message: Message) -> None:
    text = message.text or ""
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return

        odometer = parse_odometer(text)
        if odometer is None and _was_asked_for_odometer(message.chat.id):
            odometer = parse_bare_odometer(text)
        if odometer is not None:
            _awaiting_odometer.pop(message.chat.id, None)
            await _handle_odometer(message, db, user, odometer)
            return

        refuel = parse_refuel(text)
        if refuel is not None:
            await _handle_refuel(
                message,
                db,
                user,
                PendingRefuel(date=dt.date.today(), **refuel),
            )
            return

        expense = parse_quick_expense(text)
        if expense is not None:
            await _handle_expense(message, db, user, expense)
            return

        await message.answer(UNKNOWN_TEXT, reply_markup=MAIN_KEYBOARD)


async def _handle_odometer(message: Message, db: Session, user: User, value: int) -> None:
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    if len(cars) == 1:
        await _apply_odometer(message, db, cars[0].id, value, user)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_car_label(car, user), callback_data=f"odo:{car.id}:{value}"
                )
            ]
            for car in cars
        ]
    )
    await message.answer(
        f"Для якого авто оновити пробіг до {value} км?", reply_markup=keyboard
    )


async def _apply_odometer(
    message: Message, db: Session, car_id: int, value: int, user: Optional[User] = None
) -> None:
    """Update the odometer forward-only and reply with nearest intervals."""
    result = service.update_odometer(db, car_id, value)
    if result is None:
        await message.answer("Авто не знайдено.")
        return
    if not result.updated:
        await message.answer(
            f"Не можу оновити: новий пробіг ({value} км) менший за поточний "
            f"({result.old_odometer} км), а пробіг не може зменшуватися. "
            "Перевірте значення і надішліть ще раз."
        )
        return
    lines = [
        f"Пробіг {_car_label(result.car, user)} оновлено: "
        f"{result.old_odometer} км -> {result.new_odometer} км."
    ]
    if result.top_intervals:
        lines.append("\nНайближчі ТО:")
        lines.extend(
            service.format_interval_line(interval, computed)
            for interval, computed in result.top_intervals
        )
    await message.answer("\n".join(lines))


async def _handle_expense(
    message: Message, db: Session, user: User, expense: tuple[str, float]
) -> None:
    title, amount = expense
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    pending = PendingExpense(title=title, amount=amount)
    _pending_expenses[message.chat.id] = pending
    if len(cars) == 1:
        pending.car_id = cars[0].id
        await _ask_expense_confirm(message, cars[0], pending, user)
        return
    await message.answer(
        f"До якого авто записати витрату «{title}» на {amount:.2f} грн?",
        reply_markup=_car_choice_keyboard(cars, "exp", user),
    )


async def _ask_expense_confirm(
    message: Message, car, pending: PendingExpense, user: Optional[User] = None
) -> None:
    await message.answer(
        f"Витрата: «{pending.title}» — {pending.amount:.2f} грн\n"
        f"Авто: {_car_label(car, user)}\n"
        f"Дата: {dt.date.today().isoformat()}\n\n"
        "Зберегти?",
        reply_markup=_confirm_keyboard("expok", "expno"),
    )


async def _handle_refuel(
    message: Message,
    db: Session,
    user: User,
    pending: PendingRefuel,
    progress: Optional["_Progress"] = None,
) -> None:
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    _pending_refuels[message.chat.id] = pending
    if len(cars) == 1:
        pending.car_id = cars[0].id
        await _ask_refuel_confirm(message, cars[0], pending, user, progress)
        return
    text = f"До якого авто записати заправку на {pending.total_cost:.2f} грн?"
    keyboard = _car_choice_keyboard(cars, "ref", user)
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


async def _ask_refuel_confirm(
    message: Message,
    car,
    pending: PendingRefuel,
    user: Optional[User] = None,
    progress: Optional["_Progress"] = None,
) -> None:
    lines = [
        f"Заправка: {pending.liters:.2f} л × {pending.price_per_liter:.2f} грн/л "
        f"= {pending.total_cost:.2f} грн",
        f"Авто: {_car_label(car, user)} (пробіг {car.current_odometer} км)",
        f"Дата: {pending.date.isoformat()}",
    ]
    if pending.gas_station:
        lines.append(f"АЗС: {pending.gas_station}")
    if pending.photo is not None:
        lines.append("Фото чека буде додано до запису.")
    lines.append("\nЗберегти?")
    text = "\n".join(lines)
    keyboard = _confirm_keyboard("refok", "refno")
    # Turn the «Розпізнаю чек…» message into the answer rather than leaving a
    # spent progress line above it.
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("odo:"))
async def cb_odometer(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    try:
        _, car_raw, value_raw = (callback.data or "").split(":")
        car_id, value = int(car_raw), int(value_raw)
    except ValueError:
        await callback.answer("Некоректні дані")
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, car_id) is None:
            return
        await _apply_odometer(message, db, car_id, value, user)
    await callback.answer()


def _callback_car_id(data: Optional[str]) -> Optional[int]:
    try:
        return int((data or "").split(":")[1])
    except (IndexError, ValueError):
        return None


async def _writable_car(
    callback: CallbackQuery,
    message: Message,
    db: Session,
    user: Optional[User],
    car_id: int,
):
    """The car a write callback names — but only if the user may write to it.

    Every bot write goes through here. Callback data arrives from the client,
    so the car ids a viewer was never offered are precisely the ones a
    hand-made callback would carry: hiding the button is a courtesy, this is
    the check. Roles can also change between a keyboard being drawn and
    tapped, which is the same problem arriving by an innocent route.

    Returns None when the user may not proceed, having already answered the
    callback — «Авто не знайдено» when they cannot see the car at all (the
    bot's 404, indistinguishable from a car that never existed), and the
    view-only explanation when they can see it but may not write.
    """
    car = None if user is None else service.get_car(db, user, car_id)
    if car is None:
        await callback.answer("Авто не знайдено")
        return None
    if not service.can_write_to(db, user, car):
        await message.answer(VIEW_ONLY_TEXT)
        await callback.answer()
        return None
    return car


@router.callback_query(F.data.startswith("exp:"))
async def cb_expense_car(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_expenses.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_expenses.pop(message.chat.id, None)
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        car = await _writable_car(callback, message, db, user, car_id)
        if car is None:
            return
        pending.car_id = car.id
        await _ask_expense_confirm(message, car, pending, user)
    await callback.answer()


@router.callback_query(F.data == "expok")
async def cb_expense_confirm(callback: CallbackQuery) -> None:
    """«Зберегти» tapped: this is the only place an expense is written."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    pending = _pending_expenses.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        log = service.create_quick_expense(
            db, pending.car_id, pending.title, pending.amount, author_id=user.id
        )
        await message.answer(
            f"Витрату збережено: «{pending.title}» — {pending.amount:.2f} грн "
            f"({log.date.isoformat()})."
        )
    await callback.answer()


@router.callback_query(F.data == "expno")
async def cb_expense_cancel(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    _pending_expenses.pop(message.chat.id, None)
    await message.answer(CANCELLED_TEXT)
    await callback.answer()


def _parsed_date(value: Optional[str]) -> dt.date:
    """A shop's date, or today when the reader could not find one."""
    if not value:
        return dt.date.today()
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return dt.date.today()
    # A наряд dated tomorrow is a misread, and it would sort the car's history
    # wrong forever.
    return parsed if parsed <= dt.date.today() else dt.date.today()


async def _handle_maintenance(
    message: Message,
    db: Session,
    user: User,
    pending: PendingMaintenance,
    progress: Optional["_Progress"] = None,
) -> None:
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    _pending_maintenance[message.chat.id] = pending
    if len(cars) == 1:
        pending.car_id = cars[0].id
        await _ask_maintenance_confirm(message, cars[0], pending, user, progress)
        return
    text = f"До якого авто записати ТО на {pending.total_cost:.2f} грн?"
    keyboard = _car_choice_keyboard(cars, "mnt", user)
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


# Enough for the user to see what was read; the rest is on the web, where the
# entry can also be edited.
_MAX_LISTED_ITEMS = 6


async def _ask_maintenance_confirm(
    message: Message,
    car,
    pending: PendingMaintenance,
    user: Optional[User] = None,
    progress: Optional["_Progress"] = None,
) -> None:
    lines = [f"Наряд СТО на {pending.total_cost:.2f} грн"]
    if pending.parts_cost and pending.labor_cost:
        lines.append(
            f"Запчастини: {pending.parts_cost:.2f} грн · "
            f"Роботи: {pending.labor_cost:.2f} грн"
        )
    for item in pending.items[:_MAX_LISTED_ITEMS]:
        lines.append(f"• {item}")
    if len(pending.items) > _MAX_LISTED_ITEMS:
        lines.append(f"…та ще {len(pending.items) - _MAX_LISTED_ITEMS}")
    lines.append(f"Авто: {_car_label(car, user)} (пробіг {car.current_odometer} км)")
    lines.append(f"Дата: {pending.date.isoformat()}")
    lines.append("\nЗберегти?")
    text = "\n".join(lines)
    keyboard = _confirm_keyboard("mntok", "mntno")
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("mnt:"))
async def cb_maintenance_car(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_maintenance.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_maintenance.pop(message.chat.id, None)
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        car = await _writable_car(callback, message, db, user, car_id)
        if car is None:
            return
        pending.car_id = car.id
        await _ask_maintenance_confirm(message, car, pending, user)
    await callback.answer()


@router.callback_query(F.data == "mntok")
async def cb_maintenance_confirm(callback: CallbackQuery) -> None:
    """«Зберегти» tapped: this is the only place a scanned order is written."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    pending = _pending_maintenance.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        log = service.create_maintenance(
            db,
            pending.car_id,
            items=pending.items,
            parts_cost=pending.parts_cost,
            labor_cost=pending.labor_cost,
            total_cost=pending.total_cost,
            date=pending.date,
            author_id=user.id,
        )
        await message.answer(
            f"ТО збережено: {pending.total_cost:.2f} грн, "
            f"{len(pending.items)} позицій ({log.date.isoformat()}), "
            f"пробіг {log.odometer} км."
        )
    await callback.answer()


@router.callback_query(F.data == "mntno")
async def cb_maintenance_cancel(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    _pending_maintenance.pop(message.chat.id, None)
    await message.answer(CANCELLED_TEXT)
    await callback.answer()


@router.callback_query(F.data.startswith("ref:"))
async def cb_refuel_car(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_refuels.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_refuels.pop(message.chat.id, None)
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        car = await _writable_car(callback, message, db, user, car_id)
        if car is None:
            return
        pending.car_id = car.id
        await _ask_refuel_confirm(message, car, pending, user)
    await callback.answer()


@router.callback_query(F.data == "refok")
async def cb_refuel_confirm(callback: CallbackQuery) -> None:
    """«Зберегти» tapped: this is the only place a refuel is written."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    pending = _pending_refuels.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(EXPIRED_TEXT)
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        log = service.create_refuel(
            db,
            pending.car_id,
            liters=pending.liters,
            price_per_liter=pending.price_per_liter,
            total_cost=pending.total_cost,
            date=pending.date,
            gas_station=pending.gas_station,
            photo=pending.photo,
            author_id=user.id,
        )
        suffix = " Фото чека додано." if pending.photo is not None else ""
        await message.answer(
            f"Заправку збережено: {pending.liters:.2f} л на "
            f"{pending.total_cost:.2f} грн ({log.date.isoformat()}), "
            f"пробіг {log.odometer} км.{suffix}"
        )
    await callback.answer()


@router.callback_query(F.data == "refno")
async def cb_refuel_cancel(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    _pending_refuels.pop(message.chat.id, None)
    await message.answer(CANCELLED_TEXT)
    await callback.answer()


@router.callback_query(F.data.startswith("rep:"))
async def cb_report_car(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    car_id = _callback_car_id(callback.data)
    if car_id is None:
        await callback.answer("Некоректні дані")
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        # A report only reads history, so viewers are welcome to it.
        car = None if user is None else service.get_car(db, user, car_id)
        if car is None:
            await callback.answer("Авто не знайдено")
            return
        await _send_report(message, db, car, user)
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def cb_interval_done(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    try:
        interval_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некоректні дані")
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        interval = None if user is None else service.get_interval(db, user, interval_id)
        if interval is None:
            await callback.answer("Інтервал не знайдено")
            return
        title = interval.title
        completion = service.complete_interval_now(db, interval, author_id=user.id)
        await message.answer(
            f"Записав: «{title}» виконано на {completion.log.odometer} км "
            f"({completion.log.date.isoformat()}). Відлік почато заново — "
            "деталі та вартість можна дописати у веб-додатку."
        )
    await callback.answer()


@router.message()
async def handle_unknown(message: Message) -> None:
    """Anything the handlers above left behind: a sticker, a voice note, a
    document, a location.

    Registered last on purpose — aiogram matches in order, so this is the
    only handler with no filter at all. Without it those messages got
    silence, which reads as a broken bot rather than a misunderstood one.
    """
    await message.answer(UNKNOWN_TEXT, reply_markup=MAIN_KEYBOARD)


@router.callback_query(F.data.startswith("snooze:"))
async def cb_interval_snooze(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    try:
        interval_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некоректні дані")
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        interval = None if user is None else service.get_interval(db, user, interval_id)
        if interval is None:
            await callback.answer("Інтервал не знайдено")
            return
        title = interval.title
        service.snooze_interval(db, interval)
        await message.answer(f"Добре, нагадаю про «{title}» через 7 днів.")
    await callback.answer()
