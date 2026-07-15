"""Synchronous database operations behind the Telegram bot handlers.

The bot talks to the database directly (no HTTP round-trips to the API);
every function takes an explicit Session so handlers control the lifetime
and tests can supply their own engine.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pytesseract
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import (
    ROLE_EDITOR,
    ROLE_RANK,
    list_accessible_cars,
    role_rank,
    user_role_for_car,
)
from app.models import Car, LogEntry, LogPhoto, RefuelDetails, ServiceInterval, User
from app.routers.telegram import InvalidLinkCodeError, decode_link_code
from app.services.fuel import compute_fuel_stats
from app.services.intervals import compute_interval_status, effective_avg_daily_km
from app.services.intervals_complete import IntervalCompletion, complete_interval
from app.services.ocr import ParsedReceipt
from app.services.ocr_llm import recognize_receipt
from app.services.photos import new_photo_filename, write_photo_file
from app.services.report import build_car_report
from app.services.stats import build_refuel_points, compute_analytics

NOTIFY_COOLDOWN_DAYS = 7

SNOOZE_DAYS = 7

# The weekly digest covers the seven days ending on the day it is sent — a
# Monday..Sunday calendar week, since it only ever goes out on a Sunday.
DIGEST_DAYS = 7

DIGEST_TYPE_LABELS: dict[str, str] = {
    "refuel": "заправки",
    "maintenance": "ТО",
    "repair": "ремонт",
    "expense": "інші",
}


@dataclass
class OdometerUpdate:
    """Result of a forward-only odometer update attempt."""

    car: Car
    old_odometer: int
    new_odometer: int
    updated: bool
    top_intervals: list[tuple[ServiceInterval, dict]]


@dataclass
class ReminderItem:

    car: Car
    interval: ServiceInterval
    computed: dict


@dataclass
class WeeklyDigest:
    """One car's Sunday summary, ready to send to its owner."""

    car: Car
    text: str


@dataclass
class RefuelPhoto:

    image_bytes: bytes
    content_type: str = "image/jpeg"
    original_name: Optional[str] = None


class OcrUnavailableError(RuntimeError):
    """The tesseract binary is missing on this host, so OCR cannot run."""


# Linking


def link_user_by_code(db: Session, code: str, chat_id: str) -> User:
    user_id = decode_link_code(code)
    user = db.get(User, user_id)
    if user is None:
        raise InvalidLinkCodeError("link code references an unknown user")
    previous = db.execute(
        select(User).where(User.telegram_chat_id == chat_id, User.id != user.id)
    ).scalar_one_or_none()
    if previous is not None:
        previous.telegram_chat_id = None
    user.telegram_chat_id = chat_id
    db.commit()
    return user


def unlink_chat(db: Session, chat_id: str) -> bool:
    user = get_user_by_chat(db, chat_id)
    if user is None:
        return False
    user.telegram_chat_id = None
    db.commit()
    return True


def get_user_by_chat(db: Session, chat_id: str) -> Optional[User]:
    return db.execute(
        select(User).where(User.telegram_chat_id == chat_id)
    ).scalar_one_or_none()


# Cars, odometer, quick expenses


def list_cars(db: Session, user: User) -> list[Car]:
    return list_accessible_cars(db, user)


def list_owned_cars(db: Session, user: User) -> list[Car]:
    """Only the cars this user owns — never the ones merely shared with them.

    Kept apart from ``list_cars`` for the one caller that must not see shared
    cars: ``reminder_targets``. See the note there.
    """
    return list(
        db.execute(select(Car).where(Car.user_id == user.id).order_by(Car.id))
        .scalars()
        .all()
    )


def list_writable_cars(db: Session, user: User) -> list[Car]:
    """Cars the user may log to (editor or owner).

    Used to build the car-choice keyboards of the writing flows: offering a
    button that can only ever answer «you may not» is a worse experience than
    not offering it. It is *not* the security check — see ``can_write_to``.

    The per-car role lookup is a query each, which is fine at garage scale
    (a handful of cars) and keeps one definition of «what is my role».
    """
    return [car for car in list_accessible_cars(db, user) if can_write_to(db, user, car)]


def get_car(db: Session, user: User, car_id: int) -> Optional[Car]:
    """Fetch a car the user may at least see — owned or shared with them.

    Returns None when the car does not exist *or* the user has no access to
    it: the bot answers «Авто не знайдено» to both, exactly as the API
    answers 404 to both, so neither can be used to probe for cars.

    Read access only. Anything that writes must also pass ``can_write_to``.
    """
    car = db.get(Car, car_id)
    if car is None or user_role_for_car(db, user, car) is None:
        return None
    return car


def can_write_to(db: Session, user: User, car: Car) -> bool:
    return role_rank(user_role_for_car(db, user, car)) >= ROLE_RANK[ROLE_EDITOR]


def is_shared_with(user: User, car: Car) -> bool:
    return car.user_id != user.id


def _car_avg_daily_km(db: Session, car: Car) -> float:
    """The car's effective pace: the owner's override, else the computed one."""
    logs = db.execute(select(LogEntry).where(LogEntry.car_id == car.id)).scalars().all()
    return effective_avg_daily_km(car, logs)


def car_interval_statuses(
    db: Session, car: Car, today: dt.date | None = None
) -> list[tuple[ServiceInterval, dict]]:
    avg_daily_km = _car_avg_daily_km(db, car)
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )
    statuses = [
        (
            interval,
            compute_interval_status(
                interval=interval,
                current_odometer=car.current_odometer,
                avg_daily_km=avg_daily_km,
                today=today,
            ),
        )
        for interval in intervals
    ]
    statuses.sort(key=lambda pair: pair[1]["health_pct"])
    return statuses


def update_odometer(db: Session, car_id: int, value: int) -> Optional[OdometerUpdate]:
    """Forward-only odometer update.

    Returns None for an unknown car. A value below the current odometer is
    refused (updated=False, odometer untouched); otherwise the car moves
    forward and the refreshed top-3 nearest intervals are included.
    """
    car = db.get(Car, car_id)
    if car is None:
        return None
    old_odometer = car.current_odometer
    if value < old_odometer:
        return OdometerUpdate(
            car=car,
            old_odometer=old_odometer,
            new_odometer=old_odometer,
            updated=False,
            top_intervals=[],
        )
    car.current_odometer = value
    db.commit()
    db.refresh(car)
    return OdometerUpdate(
        car=car,
        old_odometer=old_odometer,
        new_odometer=value,
        updated=True,
        top_intervals=car_interval_statuses(db, car)[:3],
    )


def create_quick_expense(
    db: Session,
    car_id: int,
    title: str,
    amount: float,
    *,
    author_id: Optional[int] = None,
) -> Optional[LogEntry]:
    """Create an expense log entry dated today at the car's current odometer.

    ``author_id`` is who typed it — on a shared car that is not necessarily
    the owner. Optional and keyword-only: it stays NULL when the caller
    genuinely does not know, which is what legacy history looks like.
    """
    car = db.get(Car, car_id)
    if car is None:
        return None
    log = LogEntry(
        car_id=car.id,
        author_id=author_id,
        type="expense",
        odometer=car.current_odometer,
        date=dt.date.today(),
        total_cost=Decimal(str(round(amount, 2))),
        notes=title,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# Refuels (typed messages and scanned receipts)


def create_refuel(
    db: Session,
    car_id: int,
    *,
    liters: float,
    price_per_liter: float,
    total_cost: float,
    date: Optional[dt.date] = None,
    gas_station: Optional[str] = None,
    photo: Optional[RefuelPhoto] = None,
    author_id: Optional[int] = None,
) -> Optional[LogEntry]:
    """Create a refuel log at the car's current odometer, in one transaction.

    The bot has no way to ask for a mid-refuel odometer reading, so the car's
    last known value is used and the tank is assumed full — the same
    assumptions the quick flows in the web app make. An attached photo is
    named inside the transaction but written only after it commits: a file
    written first would outlive a failed commit as an orphan nobody ever
    collects.
    """
    car = db.get(Car, car_id)
    if car is None:
        return None
    log = LogEntry(
        car_id=car.id,
        author_id=author_id,
        type="refuel",
        odometer=car.current_odometer,
        date=date or dt.date.today(),
        total_cost=Decimal(str(round(total_cost, 2))),
    )
    db.add(log)
    db.flush()
    db.add(
        RefuelDetails(
            log_entry_id=log.id,
            liters=Decimal(str(round(liters, 2))),
            price_per_liter=Decimal(str(round(price_per_liter, 2))),
            is_full_tank=True,
            gas_station=gas_station,
        )
    )
    photo_row: Optional[LogPhoto] = None
    if photo is not None:
        photo_row = LogPhoto(
            log_entry_id=log.id,
            filename=new_photo_filename(photo.original_name, photo.content_type),
            content_type=photo.content_type,
            size=len(photo.image_bytes),
        )
        db.add(photo_row)
    # The car's OWNER, not the author: photos live under
    # <UPLOADS_DIR>/<car owner id>/ and the API serves them from there too
    # (routers/photos._storage_owner_id). An editor's receipt on a shared car
    # must land where the API will later look for it.
    user_id = car.user_id
    db.commit()

    if photo is not None and photo_row is not None:
        try:
            write_photo_file(user_id, photo_row.filename, photo.image_bytes)
        except OSError:
            # The refuel itself is committed and worth keeping; only the row
            # pointing at the file we could not write goes back, so nothing
            # ever references a missing photo.
            db.delete(photo_row)
            db.commit()
            raise

    db.refresh(log)
    return log


def recognize_refuel(image_bytes: bytes) -> ParsedReceipt:
    """OCR a receipt photo into refuel fields.

    Wraps the OCR service so callers never have to know about tesseract: a
    missing binary surfaces as OcrUnavailableError, which the handlers turn
    into a friendly Ukrainian reply instead of a stack trace.
    """
    try:
        return recognize_receipt(image_bytes)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError("tesseract binary is not installed") from exc


def build_report(db: Session, car: Car) -> bytes:
    return build_car_report(db, car)


# Ukrainian summaries


def format_interval_line(interval: ServiceInterval, computed: dict) -> str:
    remaining: list[str] = []
    km_left = computed["km_left"]
    days_left = computed["days_left"]
    if km_left is not None:
        remaining.append(
            f"залишилось {km_left} км" if km_left >= 0 else f"прострочено на {-km_left} км"
        )
    if days_left is not None:
        remaining.append(
            f"залишилось {days_left} дн."
            if days_left >= 0
            else f"прострочено на {-days_left} дн."
        )
    detail = ", ".join(remaining) if remaining else "без прив'язки до пробігу чи дати"
    return f"- {interval.title}: {computed['health_pct']:.0f}% ({detail})"


def car_label(car: Car, user: Optional[User] = None) -> str:
    label = f"{car.brand} {car.model}"
    if user is not None and is_shared_with(user, car):
        return f"{label} (спільне)"
    return label


def status_summary(db: Session, user: User, today: dt.date | None = None) -> str:
    cars = list_cars(db, user)
    if not cars:
        return "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."
    blocks: list[str] = []
    for car in cars:
        lines = [f"{car_label(car, user)} — пробіг {car.current_odometer} км"]
        statuses = car_interval_statuses(db, car, today=today)[:3]
        if statuses:
            lines.extend(format_interval_line(interval, computed) for interval, computed in statuses)
        else:
            lines.append("- Інтервали ТО не налаштовані.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# Reminders


def reminder_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, list[ReminderItem]]]:
    """Linked users with due intervals that were not notified recently.

    An interval qualifies when its status is due_soon or overdue, its snooze
    date (if any) has passed, and last_notified_at is NULL or at least
    NOTIFY_COOLDOWN_DAYS days old. Items are grouped per user, in car order.

    **Service reminders go to the car's OWNER only** — a deliberate decision,
    not an oversight. ``list_owned_cars`` is used here rather than
    ``list_cars`` precisely to keep shared cars out.

    The reasoning: an interval is one fact about one car, but the members of
    a shared car are several people. Notifying all of them turns a single oil
    change into a message for every family member, every cooldown, forever —
    and since the buttons («Виконано» / «Нагадати через 7 днів») act on the
    shared interval, the first tap silently answers the message everyone else
    is still looking at. One car, one owner, one reminder. Members keep full
    access to the same information whenever they ask for it via /status, and
    they still get reminders about cars they own themselves.

    If this is ever revisited, per-member opt-in is the shape to reach for —
    not simply widening this query.
    """
    if today is None:
        today = dt.date.today()
    cutoff = today - dt.timedelta(days=NOTIFY_COOLDOWN_DAYS)
    users = (
        db.execute(
            select(User).where(User.telegram_chat_id.is_not(None)).order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, list[ReminderItem]]] = []
    for user in users:
        items: list[ReminderItem] = []
        # Owned cars only — see the note above.
        for car in list_owned_cars(db, user):
            for interval, computed in car_interval_statuses(db, car, today=today):
                if computed["status"] not in ("due_soon", "overdue"):
                    continue
                if interval.snoozed_until is not None and interval.snoozed_until >= today:
                    continue
                if interval.last_notified_at is not None and interval.last_notified_at > cutoff:
                    continue
                items.append(ReminderItem(car=car, interval=interval, computed=computed))
        if items:
            targets.append((user, items))
    return targets


def get_interval(db: Session, user: User, interval_id: int) -> Optional[ServiceInterval]:
    """Fetch an interval whose car belongs to the user (ownership enforced).

    Owner-only, deliberately narrower than the REST equivalent (where an
    editor may complete an interval). This backs the «Виконано» / «Нагадати
    через 7 днів» buttons, which only ever appear under a reminder — and
    reminders only ever reach the owner. Accepting an editor's crafted
    callback here would let them silence a reminder they cannot see; if
    members are given reminders one day, this is the line to widen with them.
    """
    return db.execute(
        select(ServiceInterval)
        .join(Car, ServiceInterval.car_id == Car.id)
        .where(ServiceInterval.id == interval_id, Car.user_id == user.id)
    ).scalar_one_or_none()


def complete_interval_now(
    db: Session,
    interval: ServiceInterval,
    today: dt.date | None = None,
    *,
    author_id: Optional[int] = None,
) -> IntervalCompletion:
    """Tick an interval off from a reminder button.

    Delegates to the same service the REST endpoint uses, filling in what a
    one-tap reminder cannot ask for: today's date, the car's current
    odometer and no costs (the user can edit the log in the web app).

    The author is stamped on the maintenance log afterwards rather than
    passed in: ``complete_interval`` is shared with the REST endpoint and
    owns its own transaction. Stamping here keeps that signature untouched
    while still crediting whoever tapped the button.
    """
    car = db.get(Car, interval.car_id)
    completion = complete_interval(
        db,
        interval,
        odometer=car.current_odometer,
        date=today or dt.date.today(),
    )
    if author_id is not None:
        completion.log.author_id = author_id
        db.commit()
        db.refresh(completion.log)
    return completion


def snooze_interval(
    db: Session, interval: ServiceInterval, today: dt.date | None = None
) -> None:
    """Book the date the «Нагадати через 7 днів» button promises.

    Stamping last_notified_at would be exactly what sending the reminder
    already did, which is why the button used to be a no-op. A snooze date of
    its own is the only thing that actually silences the interval for a week
    regardless of where the ordinary cooldown happens to stand.
    """
    if today is None:
        today = dt.date.today()
    interval.snoozed_until = today + dt.timedelta(days=SNOOZE_DAYS)
    db.commit()


def stamp_notified(
    db: Session, interval_ids: list[int], today: dt.date | None = None
) -> None:
    if not interval_ids:
        return
    if today is None:
        today = dt.date.today()
    intervals = (
        db.execute(select(ServiceInterval).where(ServiceInterval.id.in_(interval_ids)))
        .scalars()
        .all()
    )
    for interval in intervals:
        interval.last_notified_at = today
    db.commit()


def latest_log_date(db: Session, user: User) -> Optional[dt.date]:
    return db.execute(
        select(func.max(LogEntry.date))
        .join(Car, LogEntry.car_id == Car.id)
        .where(Car.user_id == user.id)
    ).scalar_one_or_none()


# Weekly digest


def digest_window(today: dt.date) -> tuple[dt.date, dt.date]:
    return today - dt.timedelta(days=DIGEST_DAYS - 1), today


def _money(amount: float) -> str:
    return f"{amount:.2f} ₴"


def _week_distance_km(
    logs: list[LogEntry], week_logs: list[LogEntry], start: dt.date
) -> Optional[int]:
    """Km driven over the window, or None when the week cannot say.

    Measured from the last odometer known *before* the window rather than from
    the week's own first entry: otherwise everything driven up to Wednesday's
    refuel is free, and a one-entry week always reports zero.

    Extremes, not «the last row»: one mistyped odometer would otherwise make
    the distance negative and throw the week away — the same defence
    services/intervals._pace takes.
    """
    earlier = [log.odometer for log in logs if log.date < start]
    baseline = max(earlier) if earlier else min(log.odometer for log in week_logs)
    distance = max(log.odometer for log in week_logs) - baseline
    return distance if distance > 0 else None


def _week_consumption_l_100km(
    logs: list[LogEntry], car: Car, start: dt.date, end: dt.date
) -> Optional[float]:
    """Average consumption over the full-to-full segments the week CLOSED.

    The engine runs over the car's whole refuel history and the window is
    applied to its output, not to its input: a segment measured on Saturday
    usually opened before Monday, and cutting the history at the window would
    silently drop it. Averaging the engine's segments over a subset is what
    stats.compute_station_stats does per station too — the full-to-full math
    itself stays in services/fuel.py.

    Measured on the car's OWN fuel, exactly as the analytics screen's `fuel.*`
    block is: on a ГБО car a single «розхід» line can only honestly be one
    tank's, and the gas is the one the car is defined by.

    None when the week closed no segment: a week with one refuel measures
    nothing, and the digest says so by staying quiet about it.
    """
    stats = compute_fuel_stats(
        build_refuel_points(logs, car), fuel_kind=car.fuel_type
    )
    measured = [
        segment.consumption_l_100km
        for segment in stats.history
        if start <= segment.date <= end
    ]
    if not measured:
        return None
    return sum(measured) / len(measured)


def _nearest_interval_phrase(
    db: Session, car: Car, today: dt.date
) -> Optional[str]:
    statuses = car_interval_statuses(db, car, today=today)
    if not statuses:
        return None
    interval, computed = statuses[0]
    km_left, days_left = computed["km_left"], computed["days_left"]
    if km_left is not None:
        when = f"через {km_left} км" if km_left >= 0 else f"прострочено на {-km_left} км"
    elif days_left is not None:
        when = (
            f"через {days_left} дн."
            if days_left >= 0
            else f"прострочено на {-days_left} дн."
        )
    else:
        # Neither a km nor a date limit: nothing about it is «nearest».
        return None
    return f"«{interval.title}» {when}"


def build_weekly_digest(
    db: Session, car: Car, today: dt.date | None = None
) -> Optional[str]:
    """One car's week in one Ukrainian message, or None when there was no week.

    **A week with no entries produces nothing.** Not an empty digest, not a
    «нічого не сталося» — silence. A tracker that messages you about the week
    you did not use it is a tracker you mute, and the flag it would cost us is
    the one that also silences the weeks worth reading.

    Every number is the week's own, and every one of them comes from the
    service that owns it: spend from stats.compute_analytics, consumption from
    the full-to-full engine in services/fuel.py, the nearest ТО from
    services/intervals.py. Lines the week cannot measure are left out rather
    than filled with a dash.
    """
    if today is None:
        today = dt.date.today()
    start, end = digest_window(today)

    logs = list(
        db.execute(select(LogEntry).where(LogEntry.car_id == car.id)).scalars().all()
    )
    week_logs = [log for log in logs if start <= log.date <= end]
    if not week_logs:
        return None

    # The analytics engine over a window: with only the week's logs in, its
    # «all_time» total and by_type breakdown *are* the week's — the key names
    # describe the input set, not the calendar.
    totals = compute_analytics(week_logs, car, today=end)["totals"]
    breakdown = ", ".join(
        f"{DIGEST_TYPE_LABELS[log_type]} {_money(amount)}"
        for log_type, amount in totals["by_type"].items()
        if amount > 0
    )
    spent = f"Витрачено {_money(totals['all_time'])}"

    lines = [
        f"📊 Тиждень з Kapot — {car_label(car)}",
        f"{spent} ({breakdown})" if breakdown else spent,
    ]
    distance_km = _week_distance_km(logs, week_logs, start)
    if distance_km is not None:
        lines.append(f"Пробіг: +{distance_km} км")
    consumption = _week_consumption_l_100km(logs, car, start, end)
    if consumption is not None:
        lines.append(f"Середній розхід: {consumption:.1f} л/100км")
    nearest = _nearest_interval_phrase(db, car, today)
    if nearest is not None:
        lines.append(f"Найближче ТО: {nearest}")
    return "\n".join(lines)


def digest_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, list[WeeklyDigest]]]:
    """Linked, opted-in users with a week worth reporting, grouped per user.

    **One message per car, to the car's OWNER only** — the same policy
    ``reminder_targets`` documents at length, and for the same reason: a week
    is one fact about one car, and mailing every member of a shared car the
    same summary turns one Sunday into five. Members see the identical numbers
    in the web app's analytics whenever they ask, and get digests about the
    cars they own themselves.

    Cars whose week was empty are dropped individually, so a busy car still
    reports while the one in the garage stays quiet.
    """
    if today is None:
        today = dt.date.today()
    users = (
        db.execute(
            select(User)
            .where(User.telegram_chat_id.is_not(None), User.digest_enabled.is_(True))
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, list[WeeklyDigest]]] = []
    for user in users:
        digests: list[WeeklyDigest] = []
        # Owned cars only — see the note above.
        for car in list_owned_cars(db, user):
            text = build_weekly_digest(db, car, today=today)
            if text is not None:
                digests.append(WeeklyDigest(car=car, text=text))
        if digests:
            targets.append((user, digests))
    return targets


def set_digest_enabled(db: Session, user: User, enabled: bool) -> None:
    user.digest_enabled = enabled
    db.commit()
