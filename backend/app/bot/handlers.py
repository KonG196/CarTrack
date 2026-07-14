"""Aiogram v3 handlers: linking, /status, odometer updates, quick expenses."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.orm import Session

from app.bot import service
from app.bot.parsers import parse_odometer, parse_quick_expense
from app.database import SessionLocal
from app.models import User
from app.routers.telegram import InvalidLinkCodeError

router = Router()

# Pending quick expenses awaiting a car choice, keyed by chat id. Keeping the
# title out of the callback payload sidesteps Telegram's 64-byte data limit.
_pending_expenses: dict[int, tuple[str, float]] = {}

LINK_HINT = (
    "Щоб прив'язати акаунт, відкрийте веб-додаток Kapot Tracker, розділ «Гараж», "
    "згенеруйте код і надішліть його сюди командою:\n/start <код>"
)

NOT_LINKED_TEXT = "Ваш Telegram ще не прив'язано до акаунта Kapot Tracker.\n\n" + LINK_HINT

HELP_TEXT = (
    "Доступні команди:\n"
    "/start <код> — прив'язати акаунт Kapot Tracker\n"
    "/status — стан авто та найближчі ТО\n"
    "/help — ця довідка\n\n"
    "Також можна просто надіслати:\n"
    "- число (наприклад, 123456) — оновити пробіг;\n"
    "- «назва сума» (наприклад, мийка 300) — швидка витрата."
)

UNKNOWN_TEXT = (
    "Не зрозумів повідомлення. Надішліть пробіг числом (наприклад, 123456), "
    "швидку витрату у форматі «мийка 300» або /help для довідки."
)

NO_CARS_TEXT = "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."


def _car_label(car) -> str:
    return f"{car.brand} {car.model}"


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
                f"- {_car_label(car)}, {car.current_odometer} км" for car in cars
            )
            await message.answer(
                "Акаунт прив'язано! Ваші авто:\n"
                f"{car_lines}\n\n"
                "Надішліть /help, щоб побачити всі можливості."
            )
        else:
            await message.answer(
                "Акаунт прив'язано! У гаражі поки немає авто — додайте перше "
                "у веб-додатку Kapot Tracker."
            )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Show the command summary."""
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Per-car odometer + up to three nearest service intervals."""
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return
        await message.answer(service.status_summary(db, user))


@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Route plain text: odometer number, quick expense or a short hint."""
    text = message.text or ""
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(NOT_LINKED_TEXT)
            return

        odometer = parse_odometer(text)
        if odometer is not None:
            await _handle_odometer(message, db, user, odometer)
            return

        expense = parse_quick_expense(text)
        if expense is not None:
            await _handle_expense(message, db, user, expense)
            return

        await message.answer(UNKNOWN_TEXT)


async def _handle_odometer(message: Message, db: Session, user: User, value: int) -> None:
    """Apply an odometer update or offer a car choice keyboard."""
    cars = service.list_cars(db, user)
    if not cars:
        await message.answer(NO_CARS_TEXT)
        return
    if len(cars) == 1:
        await _apply_odometer(message, db, cars[0].id, value)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_car_label(car), callback_data=f"odo:{car.id}:{value}"
                )
            ]
            for car in cars
        ]
    )
    await message.answer(
        f"Для якого авто оновити пробіг до {value} км?", reply_markup=keyboard
    )


async def _apply_odometer(message: Message, db: Session, car_id: int, value: int) -> None:
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
        f"Пробіг {_car_label(result.car)} оновлено: "
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
    """Create a quick expense or offer a car choice keyboard."""
    title, amount = expense
    cars = service.list_cars(db, user)
    if not cars:
        await message.answer(NO_CARS_TEXT)
        return
    if len(cars) == 1:
        await _apply_expense(message, db, cars[0].id, title, amount)
        return
    _pending_expenses[message.chat.id] = (title, amount)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_car_label(car), callback_data=f"exp:{car.id}:{amount}"
                )
            ]
            for car in cars
        ]
    )
    await message.answer(
        f"До якого авто записати витрату «{title}» на {amount:.2f} грн?",
        reply_markup=keyboard,
    )


async def _apply_expense(
    message: Message, db: Session, car_id: int, title: str, amount: float
) -> None:
    """Persist the quick expense and confirm."""
    log = service.create_quick_expense(db, car_id, title, amount)
    if log is None:
        await message.answer("Авто не знайдено.")
        return
    await message.answer(
        f"Витрату збережено: «{title}» — {amount:.2f} грн ({log.date.isoformat()})."
    )


@router.callback_query(F.data.startswith("odo:"))
async def cb_odometer(callback: CallbackQuery) -> None:
    """Car chosen for an odometer update: odo:<car_id>:<value>."""
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
        if user is None or service.get_car(db, user, car_id) is None:
            await callback.answer("Авто не знайдено")
            return
        await _apply_odometer(message, db, car_id, value)
    await callback.answer()


@router.callback_query(F.data.startswith("exp:"))
async def cb_expense(callback: CallbackQuery) -> None:
    """Car chosen for a quick expense: exp:<car_id>:<amount> (title cached)."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Повідомлення застаріло")
        return
    try:
        _, car_raw, amount_raw = (callback.data or "").split(":")
        car_id, amount = int(car_raw), float(amount_raw)
    except ValueError:
        await callback.answer("Некоректні дані")
        return
    pending = _pending_expenses.pop(message.chat.id, None)
    if pending is None:
        await message.answer(
            "Витрата застаріла. Надішліть її ще раз, наприклад: мийка 300"
        )
        await callback.answer()
        return
    title, _pending_amount = pending
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None or service.get_car(db, user, car_id) is None:
            await callback.answer("Авто не знайдено")
            return
        await _apply_expense(message, db, car_id, title, amount)
    await callback.answer()
