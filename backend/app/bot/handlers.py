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
from app.bot import admin as bot_admin
from app.bot.ai_intent import parse_message_intent, refuel_fields_from_intent
from app.bot.parsers import (
    parse_bare_odometer,
    parse_odometer,
    parse_quick_expense,
    parse_refuel,
)
from app import backup
from app.config import settings
from app.currency import currency_symbol
from app.database import SessionLocal
from app.i18n import normalize_lang, t
from app.models import User
from app.routers.telegram import InvalidLinkCodeError

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
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

# Persistent keys under the input field. Commands still work, but nothing has
# to be remembered or typed: the two everyday actions sit one tap away and the
# rest hide behind a menu so the keyboard stays two rows tall. Labels are a
# function of language, and each label also fires its handler — so the matcher
# accepts either language's label (a user can switch UI language mid-chat and
# the keyboard already on screen must still work).
_BTN = {
    name: {t(key, "en"), t(key, "uk")}
    for name, key in {
        "refuel": "bot.h.btnRefuel",
        "odometer": "bot.h.btnOdometer",
        "expense": "bot.h.btnExpense",
        "status": "bot.h.btnStatus",
        "report": "bot.h.btnReport",
        "help": "bot.h.btnHelp",
    }.items()
}


def main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("bot.h.btnRefuel", lang)),
                KeyboardButton(text=t("bot.h.btnOdometer", lang)),
                KeyboardButton(text=t("bot.h.btnExpense", lang)),
            ],
            [
                KeyboardButton(text=t("bot.h.btnStatus", lang)),
                KeyboardButton(text=t("bot.h.btnReport", lang)),
                KeyboardButton(text=t("bot.h.btnHelp", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _not_linked(message: Message) -> str:
    """The «not linked yet» reply, in the Telegram client's language.

    Shown only when there is no linked User, so the app language is unknown —
    fall back to the language the Telegram client reports.
    """
    lang = normalize_lang(getattr(message.from_user, "language_code", None))
    return t("bot.h.notLinkedIntro", lang) + "\n\n" + t("bot.h.linkHint", lang)


def _cur(user: Optional[User]) -> str:
    return currency_symbol(user.currency if user else "USD")


def _car_label(car, user: Optional[User] = None) -> str:
    return service.car_label(car, user)


async def _refuse_write(message: Message, db: Session, user: User) -> None:
    """Explain why there is nothing to write to: no cars at all, or view-only.

    Both answers are true and neither leaks: a user with no access to a car
    never reaches this at all — they are told «Авто не знайдено», the same
    thing they hear about a car that does not exist.
    """
    lang = normalize_lang(user.language)
    if service.list_cars(db, user):
        await message.answer(t("bot.h.viewOnly", lang))
    else:
        await message.answer(t("bot.h.noCars", lang))


def _confirm_keyboard(
    confirm_data: str, cancel_data: str, lang: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("bot.h.saveButton", lang), callback_data=confirm_data
                ),
                InlineKeyboardButton(
                    text=t("bot.h.cancelButton", lang), callback_data=cancel_data
                ),
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
        lang = normalize_lang(getattr(message.from_user, "language_code", None))
        await message.answer(t("bot.h.linkHint", lang))
        return
    with SessionLocal() as db:
        try:
            user = service.link_user_by_code(db, code, str(message.chat.id))
        except InvalidLinkCodeError:
            lang = normalize_lang(getattr(message.from_user, "language_code", None))
            await message.answer(t("bot.h.invalidCode", lang))
            return
        lang = normalize_lang(user.language)
        cars = service.list_cars(db, user)
        if cars:
            car_lines = "\n".join(
                t("bot.h.carLine", lang, label=_car_label(car, user), odometer=car.current_odometer)
                for car in cars
            )
            await message.answer(
                t("bot.h.linkedWithCars", lang, cars=car_lines),
                reply_markup=main_keyboard(lang),
            )
        else:
            await message.answer(
                t("bot.h.linkedNoCars", lang),
                reply_markup=main_keyboard(lang),
            )


@router.message(F.text.in_(_BTN["refuel"]))
async def key_refuel(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    await message.answer(t("bot.h.askRefuel", lang))


@router.message(F.text.in_(_BTN["odometer"]))
async def key_odometer(message: Message) -> None:
    _awaiting_odometer[message.chat.id] = time.monotonic()
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    await message.answer(t("bot.h.askOdometer", lang))


@router.message(F.text.in_(_BTN["status"]))
async def key_status(message: Message) -> None:
    await cmd_status(message)


@router.message(F.text.in_(_BTN["expense"]))
async def key_expense(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    await message.answer(t("bot.h.askExpense", lang))


@router.message(F.text.in_(_BTN["report"]))
async def key_report(message: Message) -> None:
    await cmd_report(message)


@router.message(F.text.in_(_BTN["help"]))
async def key_help(message: Message) -> None:
    await cmd_help(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    await message.answer(t("bot.h.help", lang), reply_markup=main_keyboard(lang))


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)
        await message.answer(
            service.status_summary(db, user), reply_markup=main_keyboard(lang)
        )


@router.message(Command("digest"))
async def cmd_digest(message: Message, command: CommandObject) -> None:
    argument = (command.args or "").strip().lower()
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)
        if argument in ("on", "off"):
            enabled = argument == "on"
            service.set_digest_enabled(db, user, enabled)
            await message.answer(
                t("bot.h.digestOn", lang) if enabled else t("bot.h.digestOff", lang)
            )
            return
        state = t(
            "bot.h.digestStateOn" if user.digest_enabled else "bot.h.digestStateOff",
            lang,
        )
        await message.answer(t("bot.h.digestState", lang, state=state))


@router.message(Command("note"))
async def cmd_note(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)

        if text:
            car = service.set_scratchpad(db, user, text)
            if car is None:
                owned = service.list_owned_cars(db, user)
                if not owned:
                    await message.answer(t("bot.h.noteNoCars", lang))
                else:
                    await message.answer(t("bot.h.noteMultiCar", lang))
                return
            await message.answer(
                t("bot.h.noteSaved", lang, label=service.car_label(car, user))
            )
            return

        pads = [
            (car, note)
            for car, note in service.get_scratchpads(db, user)
            if note and note.strip()
        ]
        if not pads:
            await message.answer(t("bot.h.noteEmpty", lang))
            return
        if len(pads) == 1:
            await message.answer(f"📝 {pads[0][1]}")
        else:
            blocks = [
                f"📝 {service.car_label(car, user)}:\n{note}" for car, note in pads
            ]
            await message.answer("\n\n".join(blocks))


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is None:
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)
        # Checked before the download and the OCR: a viewer's photo can never
        # become a log entry, so there is nothing to spend tesseract on.
        if not service.list_writable_cars(db, user):
            await _refuse_write(message, db, user)
            return

        buffer = io.BytesIO()
        # The last PhotoSize is the largest one Telegram kept.
        await bot.download(message.photo[-1], destination=buffer)
        image_bytes = buffer.getvalue()

        async with _Progress(message, t("bot.h.recognizingPhoto", lang)) as progress:
            try:
                # OCR is CPU-bound and slow: keep the event loop free for other
                # chats while tesseract works.
                reading = await asyncio.to_thread(service.recognize_photo, image_bytes, lang)
            except service.OcrUnavailableError:
                await progress.finish(t("bot.h.ocrUnavailable", lang))
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
                        t("bot.h.ocrPartialTotal", lang, total=parsed.total_cost, currency=_cur(user))
                    )
                    return
                await progress.finish(t("bot.h.ocrFailed", lang))
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
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)
        cars = service.list_cars(db, user)
        if not cars:
            await message.answer(t("bot.h.noCars", lang))
            return
        if len(cars) == 1:
            await _send_report(message, db, cars[0], user)
            return
        await message.answer(
            t("bot.h.whichCarReport", lang),
            reply_markup=_car_choice_keyboard(cars, "rep", user),
        )


async def _send_report(
    message: Message, db: Session, car, user: Optional[User] = None
) -> None:
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    currency = user.currency if user else "USD"
    units = user.unit_system if user else "metric"
    pdf_bytes = await asyncio.to_thread(service.build_report, db, car, lang, currency, units)
    document = BufferedInputFile(
        pdf_bytes, filename=f"kapot-tracker-report-{car.id}.pdf"
    )
    await message.answer_document(
        document, caption=t("bot.h.reportCaption", lang, label=_car_label(car, user))
    )


@router.message(Command("backup"))
async def cmd_backup(message: Message) -> None:
    """On-demand DB backup, admin only. The dump holds EVERY user's data, so it
    goes only to the configured admin chat — and only the admin may ask for it.
    Replaces the old daily auto-push; now it is pull-only (here or in the app)."""
    lang = normalize_lang(getattr(message.from_user, "language_code", None))
    admin_chat = settings.BACKUP_TELEGRAM_CHAT_ID
    if not admin_chat or str(message.chat.id) != admin_chat:
        await message.answer(t("bot.h.adminOnly", lang))
        return
    progress = await message.answer(t("bot.h.backupPreparing", lang))
    try:
        path = await asyncio.to_thread(backup.create_backup)
        await asyncio.to_thread(
            backup.rotate_backups, Path(settings.BACKUP_DIR), settings.BACKUP_KEEP
        )
        await backup.send_backup_via_telegram(path, bot=message.bot)
        await progress.delete()
    except Exception:
        logger.exception("Manual backup failed")
        await progress.edit_text(t("bot.h.backupFailed", lang))


def _admin_lang(user: Optional[User], message: Message) -> str:
    return (
        normalize_lang(user.language)
        if user
        else normalize_lang(getattr(message.from_user, "language_code", None))
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Toggle owner-only admin mode. Gated by is_superadmin, so a non-owner who
    discovers the command sees only the plain rejection."""
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = _admin_lang(user, message)
    if user is None or not user.is_superadmin:
        await message.answer(t("bot.admin.notAdmin", lang))
        return
    chat_id = message.chat.id
    if bot_admin.is_admin_mode(chat_id):
        bot_admin.set_admin_mode(chat_id, False)
        await message.answer(t("bot.admin.off", lang))
        return
    bot_admin.set_admin_mode(chat_id, True)
    await message.answer(
        t("bot.admin.on", lang) + "\n\n" + t("bot.admin.menuTitle", lang),
        reply_markup=bot_admin.menu_keyboard(lang),
    )


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
            await message.answer(_not_linked(message))
            return
        lang = normalize_lang(user.language)

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

        # Deterministic parsers missed — let the model read the free text and
        # pick the action. Off the event loop (httpx is sync) and best-effort:
        # a None/quota/timeout just falls through to «не зрозумів».
        if settings.GEMINI_API_KEY:
            intent = await asyncio.to_thread(parse_message_intent, text)
            if intent and await _handle_intent(message, db, user, intent):
                return

        await message.answer(t("bot.h.unknown", lang), reply_markup=main_keyboard(lang))


async def _handle_intent(message: Message, db: Session, user: User, intent: dict) -> bool:
    """Route an LLM-parsed free-text message; True once it produced an entry."""
    action = intent.get("action")
    if action == "odometer":
        odometer = intent.get("odometer")
        if isinstance(odometer, (int, float)) and not isinstance(odometer, bool) and odometer > 0:
            await _handle_odometer(message, db, user, int(odometer))
            return True
        return False
    if action == "refuel":
        fields = refuel_fields_from_intent(intent)
        if fields is None:
            return False
        await _handle_refuel(message, db, user, PendingRefuel(date=dt.date.today(), **fields))
        return True
    if action == "expense":
        title = (intent.get("title") or "").strip()
        amount = intent.get("total_cost")
        if title and isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0:
            await _handle_expense(message, db, user, (title, float(amount)))
            return True
        return False
    return False


async def _handle_odometer(message: Message, db: Session, user: User, value: int) -> None:
    lang = normalize_lang(user.language)
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
        t("bot.h.whichCarOdometer", lang, value=value), reply_markup=keyboard
    )


async def _apply_odometer(
    message: Message, db: Session, car_id: int, value: int, user: Optional[User] = None
) -> None:
    """Update the odometer forward-only and reply with nearest intervals."""
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    result = service.update_odometer(db, car_id, value)
    if result is None:
        await message.answer(t("bot.h.carNotFound", lang))
        return
    if not result.updated:
        await message.answer(
            t(
                "bot.h.odometerBackwards",
                lang,
                value=value,
                old=result.old_odometer,
            )
        )
        return
    lines = [
        t(
            "bot.h.odometerUpdated",
            lang,
            label=_car_label(result.car, user),
            old=result.old_odometer,
            new=result.new_odometer,
        )
    ]
    if result.top_intervals:
        lines.append(t("bot.h.upcomingService", lang))
        lines.extend(
            service.format_interval_line(interval, computed)
            for interval, computed in result.top_intervals
        )
    await message.answer("\n".join(lines))


async def _handle_expense(
    message: Message, db: Session, user: User, expense: tuple[str, float]
) -> None:
    title, amount = expense
    lang = normalize_lang(user.language)
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
        t("bot.h.whichCarExpense", lang, title=title, amount=amount, currency=_cur(user)),
        reply_markup=_car_choice_keyboard(cars, "exp", user),
    )


async def _ask_expense_confirm(
    message: Message, car, pending: PendingExpense, user: Optional[User] = None
) -> None:
    lang = normalize_lang(user.language) if user else normalize_lang(None)
    await message.answer(
        t(
            "bot.h.expenseConfirm",
            lang,
            currency=_cur(user),
            title=pending.title,
            amount=pending.amount,
            label=_car_label(car, user),
            date=dt.date.today().isoformat(),
        ),
        reply_markup=_confirm_keyboard("expok", "expno", lang),
    )


async def _handle_refuel(
    message: Message,
    db: Session,
    user: User,
    pending: PendingRefuel,
    progress: Optional["_Progress"] = None,
) -> None:
    lang = normalize_lang(user.language)
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    _pending_refuels[message.chat.id] = pending
    if len(cars) == 1:
        pending.car_id = cars[0].id
        await _ask_refuel_confirm(message, cars[0], pending, user, progress)
        return
    text = t("bot.h.whichCarRefuel", lang, total=pending.total_cost, currency=_cur(user))
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
    lang = normalize_lang(user.language) if user else normalize_lang(None)
    lines = [
        t(
            "bot.h.refuelLine",
            lang,
            currency=_cur(user),
            liters=pending.liters,
            price=pending.price_per_liter,
            total=pending.total_cost,
        ),
        t(
            "bot.h.carWithOdometer",
            lang,
            label=_car_label(car, user),
            odometer=car.current_odometer,
        ),
        t("bot.h.dateLine", lang, date=pending.date.isoformat()),
    ]
    if pending.gas_station:
        lines.append(t("bot.h.stationLine", lang, station=pending.gas_station))
    if pending.photo is not None:
        lines.append(t("bot.h.photoWillBeAdded", lang))
    lines.append(t("bot.h.savePrompt", lang))
    text = "\n".join(lines)
    keyboard = _confirm_keyboard("refok", "refno", lang)
    # Turn the «Розпізнаю чек…» message into the answer rather than leaving a
    # spent progress line above it.
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("odo:"))
async def cb_odometer(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    try:
        _, car_raw, value_raw = (callback.data or "").split(":")
        car_id, value = int(car_raw), int(value_raw)
    except ValueError:
        await callback.answer(t("bot.h.badData", lang))
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, car_id) is None:
            return
        await _apply_odometer(message, db, car_id, value, user)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(callback: CallbackQuery) -> None:
    """Render an admin page in place. Re-checks is_superadmin every time — the
    callback data is client-supplied, and admin rights can change between the
    keyboard being drawn and a button being tapped."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        lang = _admin_lang(user, message)
        if user is None or not user.is_superadmin:
            await callback.answer(t("bot.admin.notAdmin", lang), show_alert=True)
            return
        try:
            _, kind, page_raw = (callback.data or "").split(":")
            page_index = max(0, int(page_raw))
        except ValueError:
            await callback.answer(t("bot.h.badData", lang))
            return

        if kind == "close":
            try:
                await message.edit_text(t("bot.admin.closed", lang))
            except TelegramBadRequest:
                pass
            await callback.answer()
            return

        if kind == "menu":
            try:
                await message.edit_text(
                    t("bot.admin.menuTitle", lang),
                    reply_markup=bot_admin.menu_keyboard(lang),
                )
            except TelegramBadRequest:
                pass
            await callback.answer()
            return

        if kind == "stats":
            text = bot_admin.format_stats(service.admin_stats(db), lang)
            keyboard = bot_admin.menu_keyboard(lang)
        elif kind == "users":
            total = service.admin_count_users(db)
            pages = max(1, (total + bot_admin._ADMIN_PAGE - 1) // bot_admin._ADMIN_PAGE)
            page_index = min(page_index, pages - 1)
            rows = service.admin_list_users(
                db, page_index * bot_admin._ADMIN_PAGE, bot_admin._ADMIN_PAGE
            )
            text = bot_admin.format_users(
                db, rows, page_index + 1, pages, total, lang
            )
            keyboard = bot_admin.page_keyboard("users", page_index + 1, pages, lang)
        elif kind == "cars":
            total = service.admin_count_cars(db)
            pages = max(1, (total + bot_admin._ADMIN_PAGE - 1) // bot_admin._ADMIN_PAGE)
            page_index = min(page_index, pages - 1)
            rows = service.admin_list_cars(
                db, page_index * bot_admin._ADMIN_PAGE, bot_admin._ADMIN_PAGE
            )
            text = bot_admin.format_cars(rows, page_index + 1, pages, total, lang)
            keyboard = bot_admin.page_keyboard("cars", page_index + 1, pages, lang)
        else:
            await callback.answer(t("bot.h.badData", lang))
            return

    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # Telegram rejects an edit to identical text/markup — e.g. tapping the
        # same page twice. Nothing to change; just acknowledge the tap.
        pass
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
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(callback.from_user, "language_code", None)
    )
    car = None if user is None else service.get_car(db, user, car_id)
    if car is None:
        await callback.answer(t("bot.h.carNotFoundToast", lang))
        return None
    if not service.can_write_to(db, user, car):
        await message.answer(t("bot.h.viewOnly", lang))
        await callback.answer()
        return None
    return car


@router.callback_query(F.data.startswith("exp:"))
async def cb_expense_car(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_expenses.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_expenses.pop(message.chat.id, None)
        await message.answer(t("bot.h.expired", lang))
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
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    pending = _pending_expenses.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(t("bot.h.expired", lang))
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        lang = normalize_lang(user.language)
        log = service.create_quick_expense(
            db, pending.car_id, pending.title, pending.amount, author_id=user.id
        )
        await message.answer(
            t(
                "bot.h.expenseSaved",
                lang,
                currency=_cur(user),
                title=pending.title,
                amount=pending.amount,
                date=log.date.isoformat(),
            )
        )
    await callback.answer()


@router.callback_query(F.data == "expno")
async def cb_expense_cancel(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    _pending_expenses.pop(message.chat.id, None)
    await message.answer(t("bot.h.cancelled", lang))
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
    lang = normalize_lang(user.language)
    cars = service.list_writable_cars(db, user)
    if not cars:
        await _refuse_write(message, db, user)
        return
    _pending_maintenance[message.chat.id] = pending
    if len(cars) == 1:
        pending.car_id = cars[0].id
        await _ask_maintenance_confirm(message, cars[0], pending, user, progress)
        return
    text = t("bot.h.whichCarMaintenance", lang, total=pending.total_cost, currency=_cur(user))
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
    lang = normalize_lang(user.language) if user else normalize_lang(None)
    lines = [t("bot.h.maintenanceHeader", lang, total=pending.total_cost, currency=_cur(user))]
    if pending.parts_cost and pending.labor_cost:
        lines.append(
            t(
                "bot.h.maintenancePartsLabor",
                lang,
                currency=_cur(user),
                parts=pending.parts_cost,
                labor=pending.labor_cost,
            )
        )
    for item in pending.items[:_MAX_LISTED_ITEMS]:
        lines.append(f"• {item}")
    if len(pending.items) > _MAX_LISTED_ITEMS:
        lines.append(
            t("bot.h.maintenanceMore", lang, count=len(pending.items) - _MAX_LISTED_ITEMS)
        )
    lines.append(
        t(
            "bot.h.carWithOdometer",
            lang,
            label=_car_label(car, user),
            odometer=car.current_odometer,
        )
    )
    lines.append(t("bot.h.dateLine", lang, date=pending.date.isoformat()))
    lines.append(t("bot.h.savePrompt", lang))
    text = "\n".join(lines)
    keyboard = _confirm_keyboard("mntok", "mntno", lang)
    if progress is not None:
        await progress.finish(text, reply_markup=keyboard)
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("mnt:"))
async def cb_maintenance_car(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_maintenance.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_maintenance.pop(message.chat.id, None)
        await message.answer(t("bot.h.expired", lang))
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
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    pending = _pending_maintenance.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(t("bot.h.expired", lang))
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        lang = normalize_lang(user.language)
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
            t(
                "bot.h.maintenanceSaved",
                lang,
                currency=_cur(user),
                total=pending.total_cost,
                count=len(pending.items),
                date=log.date.isoformat(),
                odometer=log.odometer,
            )
        )
    await callback.answer()


@router.callback_query(F.data == "mntno")
async def cb_maintenance_cancel(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    _pending_maintenance.pop(message.chat.id, None)
    await message.answer(t("bot.h.cancelled", lang))
    await callback.answer()


@router.callback_query(F.data.startswith("ref:"))
async def cb_refuel_car(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    car_id = _callback_car_id(callback.data)
    pending = _pending_refuels.get(message.chat.id)
    if car_id is None or pending is None:
        _pending_refuels.pop(message.chat.id, None)
        await message.answer(t("bot.h.expired", lang))
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
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    pending = _pending_refuels.pop(message.chat.id, None)
    if pending is None or pending.car_id is None:
        await message.answer(t("bot.h.expired", lang))
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if await _writable_car(callback, message, db, user, pending.car_id) is None:
            return
        lang = normalize_lang(user.language)
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
        suffix = t("bot.h.refuelPhotoSuffix", lang) if pending.photo is not None else ""
        await message.answer(
            t(
                "bot.h.refuelSaved",
                lang,
                currency=_cur(user),
                liters=pending.liters,
                total=pending.total_cost,
                date=log.date.isoformat(),
                odometer=log.odometer,
                suffix=suffix,
            )
        )
    await callback.answer()


@router.callback_query(F.data == "refno")
async def cb_refuel_cancel(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    _pending_refuels.pop(message.chat.id, None)
    await message.answer(t("bot.h.cancelled", lang))
    await callback.answer()


@router.callback_query(F.data.startswith("rep:"))
async def cb_report_car(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    car_id = _callback_car_id(callback.data)
    if car_id is None:
        await callback.answer(t("bot.h.badData", lang))
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        # A report only reads history, so viewers are welcome to it.
        car = None if user is None else service.get_car(db, user, car_id)
        if car is None:
            await callback.answer(t("bot.h.carNotFoundToast", lang))
            return
        await _send_report(message, db, car, user)
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def cb_interval_done(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    try:
        interval_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer(t("bot.h.badData", lang))
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is not None:
            lang = normalize_lang(user.language)
        interval = None if user is None else service.get_interval(db, user, interval_id)
        if interval is None:
            await callback.answer(t("bot.h.intervalNotFound", lang))
            return
        title = interval.title
        completion = service.complete_interval_now(db, interval, author_id=user.id)
        await message.answer(
            t(
                "bot.h.intervalDone",
                lang,
                title=title,
                odometer=completion.log.odometer,
                date=completion.log.date.isoformat(),
            )
        )
    # Retire the button once used: without this every extra tap logs another
    # maintenance entry and re-advances the interval. Best-effort — a failed
    # edit (message too old to edit) must not undo the completion above.
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()


@router.message()
async def handle_unknown(message: Message) -> None:
    """Anything the handlers above left behind: a sticker, a voice note, a
    document, a location.

    Registered last on purpose — aiogram matches in order, so this is the
    only handler with no filter at all. Without it those messages got
    silence, which reads as a broken bot rather than a misunderstood one.
    """
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = normalize_lang(user.language) if user else normalize_lang(
        getattr(message.from_user, "language_code", None)
    )
    await message.answer(t("bot.h.unknown", lang), reply_markup=main_keyboard(lang))


@router.callback_query(F.data.startswith("rotate:"))
async def cb_tire_rotate(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    try:
        tire_set_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer(t("bot.h.badData", lang))
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is not None:
            lang = normalize_lang(user.language)
        tire_set = None if user is None else service.rotate_tire_set(db, user, tire_set_id)
        if tire_set is None:
            await callback.answer(t("bot.h.rotationFailed", lang))
            return
        await message.answer(t("bot.h.tireRotated", lang))
    await callback.answer()


@router.callback_query(F.data.startswith("snooze:"))
async def cb_interval_snooze(callback: CallbackQuery) -> None:
    lang = normalize_lang(getattr(callback.from_user, "language_code", None))
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(t("bot.h.msgExpired", lang))
        return
    try:
        interval_id = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer(t("bot.h.badData", lang))
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        if user is not None:
            lang = normalize_lang(user.language)
        interval = None if user is None else service.get_interval(db, user, interval_id)
        if interval is None:
            await callback.answer(t("bot.h.intervalNotFound", lang))
            return
        title = interval.title
        service.snooze_interval(db, interval)
        await message.answer(t("bot.h.intervalSnoozed", lang, title=title))
    await callback.answer()
