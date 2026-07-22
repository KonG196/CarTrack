"""Synchronous database operations behind the Telegram bot handlers.

The bot talks to the database directly (no HTTP round-trips to the API);
every function takes an explicit Session so handlers control the lifetime
and tests can supply their own engine.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

import pytesseract
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.access import (
    ROLE_EDITOR,
    ROLE_RANK,
    list_accessible_cars,
    role_rank,
    user_role_for_car,
)
from app.i18n import normalize_lang, t
from app.models import (
    Car,
    LogEntry,
    LogPhoto,
    MaintenanceDetails,
    RefuelDetails,
    ServiceInterval,
    TireSet,
    User,
)
from app.routers.telegram import InvalidLinkCodeError, decode_link_code
from app.services import climate
from app.services.fuel import (
    ConsumptionSpike,
    compute_fuel_stats,
    compute_stats_per_kind,
    detect_consumption_spike,
)
from app.services.intervals import compute_interval_status, effective_avg_daily_km
from app.services.intervals_complete import IntervalCompletion, complete_interval
from app.services.ocr import ParsedReceipt
from app.services.tires import due_rotation_km, is_tire_age_due, tire_age_years
from app.services.ocr_llm import OcrUnavailable, PhotoReading, recognize_receipt
from app.services.ocr_llm import recognize_photo as ocr_recognize_photo
from app.services.photos import new_photo_filename, write_photo_file
from app.services.report import build_car_report
from app.services.stats import build_refuel_points, compute_analytics

NOTIFY_COOLDOWN_DAYS = 7

SNOOZE_DAYS = 7

# The weekly digest covers the seven days ending on the day it is sent — a
# Monday..Sunday calendar week, since it only ever goes out on a Sunday.
DIGEST_DAYS = 7

# Log-type → i18n key suffix for the digest / status spend breakdown. The word
# is resolved at call time in the reader's language.
_DIGEST_TYPE_KEYS: dict[str, str] = {
    "refuel": "typeRefuel",
    "maintenance": "typeMaintenance",
    "repair": "typeRepair",
    "expense": "typeExpense",
}


def _type_word(log_type: str, lang: str) -> str:
    return t(f"bot.svc.{_DIGEST_TYPE_KEYS[log_type]}", lang)


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


def create_maintenance(
    db: Session,
    car_id: int,
    *,
    items: Sequence[str],
    parts_cost: float,
    labor_cost: float,
    total_cost: float,
    date: Optional[dt.date] = None,
    author_id: Optional[int] = None,
) -> Optional[LogEntry]:
    """Write a service entry at the car's current odometer.

    The odometer is not asked for: a наряд is photographed on the way out of
    the shop, so what the car reads now is what it read on the lift, give or
    take the drive home. The user can correct it on the web.
    """
    car = db.get(Car, car_id)
    if car is None:
        return None
    log = LogEntry(
        car_id=car.id,
        author_id=author_id,
        type="maintenance",
        odometer=car.current_odometer,
        date=date or dt.date.today(),
        total_cost=Decimal(str(round(total_cost, 2))),
    )
    db.add(log)
    db.flush()
    db.add(
        MaintenanceDetails(
            log_entry_id=log.id,
            parts_cost=Decimal(str(round(parts_cost, 2))),
            labor_cost=Decimal(str(round(labor_cost, 2))),
            items=list(items),
        )
    )
    db.commit()
    db.refresh(log)
    return log


def recognize_refuel(image_bytes: bytes, lang: str = "en") -> ParsedReceipt:
    """OCR a receipt photo into refuel fields.

    Wraps the OCR service so callers never have to know about the OCR ladder: a
    missing tesseract binary or a down vision model both surface as
    OcrUnavailableError, which the handlers turn into a friendly reply instead
    of a stack trace.
    """
    try:
        return recognize_receipt(image_bytes, lang=lang)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError("tesseract binary is not installed") from exc
    except OcrUnavailable as exc:
        raise OcrUnavailableError("vision OCR is unavailable") from exc


def recognize_photo(image_bytes: bytes, lang: str = "en") -> PhotoReading:
    """OCR a photo the user sent without saying what it is.

    In a chat there is no form to pick a type in: whatever the station or the
    shop handed over gets photographed and sent, so the reader identifies it.
    Uses the same vision path as the web scan (Gemini when configured).
    """
    try:
        return ocr_recognize_photo(image_bytes, lang=lang)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError("tesseract binary is not installed") from exc
    except OcrUnavailable as exc:
        raise OcrUnavailableError("vision OCR is unavailable") from exc


def build_report(db: Session, car: Car, lang: str = "en") -> bytes:
    return build_car_report(db, car, lang)


# Ukrainian summaries


def format_interval_line(
    interval: ServiceInterval, computed: dict, lang: str = "en"
) -> str:
    # An interval falls due when EITHER its distance or its time runs out, so it
    # can be overdue on one axis while the other still has slack. Once overdue,
    # only report what is overdue — "залишилось 10 873 км" beside "прострочено"
    # read as a contradiction.
    km_left = computed["km_left"]
    days_left = computed["days_left"]
    overdue = (km_left is not None and km_left < 0) or (days_left is not None and days_left < 0)
    remaining: list[str] = []
    if km_left is not None:
        if km_left < 0:
            remaining.append(t("bot.svc.overdueKm", lang, km=-km_left))
        elif not overdue:
            remaining.append(t("bot.svc.leftKm", lang, km=km_left))
    if days_left is not None:
        if days_left < 0:
            remaining.append(t("bot.svc.overdueDays", lang, days=-days_left))
        elif not overdue:
            remaining.append(t("bot.svc.leftDays", lang, days=days_left))
    detail = ", ".join(remaining) if remaining else t("bot.svc.noLimit", lang)
    return f"- {interval.title}: {computed['health_pct']:.0f}% ({detail})"


def car_label(car: Car, user: Optional[User] = None) -> str:
    label = f"{car.brand} {car.model}"
    if user is not None and is_shared_with(user, car):
        return f"{label} {t('bot.svc.shared', normalize_lang(user.language))}"
    return label


def status_summary(db: Session, user: User, today: dt.date | None = None) -> str:
    lang = normalize_lang(user.language)
    cars = list_cars(db, user)
    if not cars:
        return t("bot.svc.emptyGarage", lang)
    blocks: list[str] = []
    for car in cars:
        lines = [
            t(
                "bot.svc.statusCarLine",
                lang,
                label=car_label(car, user),
                km=car.current_odometer,
            )
        ]
        statuses = car_interval_statuses(db, car, today=today)[:3]
        if statuses:
            lines.extend(
                format_interval_line(interval, computed, lang)
                for interval, computed in statuses
            )
        else:
            lines.append(f"- {t('bot.svc.intervalsNotSet', lang)}")
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
            select(User)
            .where(
                User.telegram_chat_id.is_not(None),
                User.reminders_enabled.is_(True),
            )
            .order_by(User.id)
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


# Consumption watchdog


#: A spike whose closing refuel is older than this is stale — the loop runs
#: daily, so a fresh jump is caught within a day; anything older is history
#: (and stops the feature spamming about old data the day it first ships).
CONSUMPTION_RECENT_DAYS = 21


@dataclass
class ConsumptionAlert:
    car: Car
    spike: ConsumptionSpike


def car_consumption_spike(db: Session, car: Car) -> Optional[ConsumptionSpike]:
    """This car's latest consumption spike against its own recent norm, if any."""
    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id, LogEntry.type == "refuel")
            .options(selectinload(LogEntry.refuel))
        )
        .scalars()
        .all()
    )
    points = build_refuel_points(logs, car)
    return detect_consumption_spike(compute_stats_per_kind(points))


def consumption_alert_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, ConsumptionAlert]]:
    """Owners whose car just showed a fresh, not-yet-reported consumption spike.

    Owner-only and reminders-gated, exactly like ``reminder_targets`` — same
    reasoning (one car, one owner). A spike is skipped once its closing refuel
    has been stamped on the car, and once it is older than CONSUMPTION_RECENT_DAYS.
    """
    if today is None:
        today = dt.date.today()
    users = (
        db.execute(
            select(User)
            .where(
                User.telegram_chat_id.is_not(None),
                User.notify_fuel.is_(True),
            )
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, ConsumptionAlert]] = []
    for user in users:
        for car in list_owned_cars(db, user):
            spike = car_consumption_spike(db, car)
            if spike is None:
                continue
            if car.consumption_alert_log_id == spike.log_id:
                continue
            if (today - spike.date).days > CONSUMPTION_RECENT_DAYS:
                continue
            targets.append((user, ConsumptionAlert(car=car, spike=spike)))
    return targets


def stamp_consumption_alert(db: Session, car: Car, log_id: int) -> None:
    car.consumption_alert_log_id = log_id
    db.commit()


# Seasonal (autumn) reminders


@dataclass
class SeasonalReminder:
    car: Car
    kind: str  # "tires" | "tires_add" | "washer"


def installed_tire_set(db: Session, car: Car) -> Optional[TireSet]:
    return db.execute(
        select(TireSet).where(
            TireSet.car_id == car.id, TireSet.is_installed.is_(True)
        )
    ).scalar_one_or_none()


def seasonal_reminder_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, SeasonalReminder]]:
    """Owners due an autumn nudge — winter tyres and/or winter washer fluid.

    Owner-only and reminders-gated like the rest. Each nudge is once per autumn
    (guarded by the year stamped on the car), fires only inside its regional
    window, and the tyre nudge only when the car is actually still on summer
    tyres. A car with NO tyre sets at all gets a «set up your tyres» nudge
    instead, so an owner who never opened the tyres screen still hears about the
    changeover. The region comes from the plate; a car with no plate falls to
    the central-Ukraine calendar.
    """
    if today is None:
        today = dt.date.today()
    users = (
        db.execute(
            select(User)
            .where(
                User.telegram_chat_id.is_not(None),
                User.notify_seasonal.is_(True),
            )
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, SeasonalReminder]] = []
    for user in users:
        for car in list_owned_cars(db, user):
            if car.tire_reminder_year != today.year and climate.tire_changeover_due(
                car.plate, today
            ):
                if not car.tire_sets:
                    # Nothing recorded — nudge them to set tyres up (CTA in the bot).
                    targets.append((user, SeasonalReminder(car=car, kind="tires_add")))
                else:
                    mounted = installed_tire_set(db, car)
                    if mounted is not None and mounted.season == "summer":
                        targets.append((user, SeasonalReminder(car=car, kind="tires")))
            if car.washer_reminder_year != today.year and climate.washer_changeover_due(
                car.plate, today
            ):
                targets.append((user, SeasonalReminder(car=car, kind="washer")))
    return targets


def stamp_seasonal(db: Session, car: Car, kind: str, year: int) -> None:
    if kind in ("tires", "tires_add"):
        car.tire_reminder_year = year
    elif kind == "washer":
        car.washer_reminder_year = year
    db.commit()


# Tire rotation nudge


@dataclass
class RotationReminder:
    car: Car
    tire_set: TireSet
    km_since_rotation: int
    due_km: int


def rotation_reminder_targets(
    db: Session,
) -> list[tuple[User, RotationReminder]]:
    """Owners whose mounted set has crossed a fresh 10k-since-rotation mark.

    Owner-only and reminders-gated. Once per 10k mark (dedup via the km stamped
    on the set), so an owner who never rotates is nudged again at 20k, 30k…
    """
    users = (
        db.execute(
            select(User)
            .where(
                User.telegram_chat_id.is_not(None),
                User.notify_rotation.is_(True),
            )
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, RotationReminder]] = []
    for user in users:
        for car in list_owned_cars(db, user):
            mounted = installed_tire_set(db, car)
            if mounted is None:
                continue
            km = mounted.km_since_rotation
            due = due_rotation_km(km, mounted.rotation_reminded_km)
            if due is None:
                continue
            targets.append(
                (
                    user,
                    RotationReminder(
                        car=car, tire_set=mounted, km_since_rotation=km, due_km=due
                    ),
                )
            )
    return targets


def stamp_rotation(db: Session, tire_set: TireSet, due_km: int) -> None:
    tire_set.rotation_reminded_km = due_km
    db.commit()


# Tire age nudge


@dataclass
class TireAgeReminder:
    car: Car
    tire_set: TireSet
    age_years: int


def tire_age_reminder_targets(
    db: Session, today: dt.date | None = None
) -> list[tuple[User, TireAgeReminder]]:
    """Owners whose mounted set has aged past the inspect-or-replace threshold.

    Owner-only and gated on notify_seasonal (the tyre-notifications toggle).
    Only the mounted set is checked — that is the rubber actually being driven
    on — and each set is nudged at most once per calendar year via the
    age_reminded_year stamp. Age comes from the DOT year (fallback: purchase
    year); a set with neither is skipped.
    """
    if today is None:
        today = dt.date.today()
    users = (
        db.execute(
            select(User)
            .where(
                User.telegram_chat_id.is_not(None),
                User.notify_seasonal.is_(True),
            )
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    targets: list[tuple[User, TireAgeReminder]] = []
    for user in users:
        for car in list_owned_cars(db, user):
            mounted = installed_tire_set(db, car)
            if mounted is None:
                continue
            age = tire_age_years(mounted.dot_year, mounted.purchased_at, today)
            if not is_tire_age_due(age):
                continue
            if mounted.age_reminded_year == today.year:
                continue
            targets.append(
                (user, TireAgeReminder(car=car, tire_set=mounted, age_years=age))
            )
    return targets


def stamp_tire_age(db: Session, tire_set: TireSet, year: int) -> None:
    tire_set.age_reminded_year = year
    db.commit()


def rotate_tire_set(db: Session, user: User, tire_set_id: int) -> Optional[TireSet]:
    """Record an axle rotation from the bot's «Зробити ротацію» button.

    Owner-only and mounted-set-only, the same rules as the web endpoint: resets
    the rotation clock to the car's current odometer so the next nudge is 10 000
    km away. Returns None when the set is missing, on the shelf, or not the
    user's to rotate.
    """
    tire_set = db.get(TireSet, tire_set_id)
    if tire_set is None or not tire_set.is_installed:
        return None
    car = db.get(Car, tire_set.car_id)
    if car is None or car.user_id != user.id:
        return None
    tire_set.odometer_at_rotation = car.current_odometer
    tire_set.rotation_reminded_km = None
    db.commit()
    return tire_set


# Driver scratchpad (/note)


def get_scratchpads(db: Session, user: User) -> list[tuple[Car, Optional[str]]]:
    """Each accessible car with its note — a member may read the gate codes too."""
    return [(car, car.scratchpad) for car in list_cars(db, user)]


def set_scratchpad(db: Session, user: User, text: str) -> Optional[Car]:
    """Write the note on the user's single owned car, or None to defer.

    None means the user owns zero cars or more than one: with several, the bot
    cannot know which to write without asking, and a wrong-car note is worse
    than sending them to the web. Editing a note is owner-only, like the rest of
    a car's configuration.
    """
    owned = list_owned_cars(db, user)
    if len(owned) != 1:
        return None
    car = owned[0]
    car.scratchpad = text
    db.commit()
    return car


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
    db: Session, car: Car, today: dt.date, lang: str = "en"
) -> Optional[str]:
    statuses = car_interval_statuses(db, car, today=today)
    if not statuses:
        return None
    interval, computed = statuses[0]
    km_left, days_left = computed["km_left"], computed["days_left"]
    if km_left is not None:
        when = (
            t("bot.svc.inKm", lang, km=km_left)
            if km_left >= 0
            else t("bot.svc.overdueKm", lang, km=-km_left)
        )
    elif days_left is not None:
        when = (
            t("bot.svc.inDays", lang, days=days_left)
            if days_left >= 0
            else t("bot.svc.overdueDays", lang, days=-days_left)
        )
    else:
        # Neither a km nor a date limit: nothing about it is «nearest».
        return None
    return f"«{interval.title}» {when}"


def build_weekly_digest(
    db: Session, car: Car, today: dt.date | None = None, lang: str = "en"
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
        f"{_type_word(log_type, lang)} {_money(amount)}"
        for log_type, amount in totals["by_type"].items()
        if amount > 0
    )
    spent = t("bot.svc.spent", lang, money=_money(totals["all_time"]))

    lines = [
        t("bot.svc.digestHeader", lang, label=car_label(car)),
        f"{spent} ({breakdown})" if breakdown else spent,
    ]
    distance_km = _week_distance_km(logs, week_logs, start)
    if distance_km is not None:
        lines.append(t("bot.svc.distance", lang, km=distance_km))
    consumption = _week_consumption_l_100km(logs, car, start, end)
    if consumption is not None:
        lines.append(t("bot.svc.consumption", lang, value=f"{consumption:.1f}"))
    nearest = _nearest_interval_phrase(db, car, today, lang)
    if nearest is not None:
        lines.append(t("bot.svc.nearest", lang, phrase=nearest))
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
        lang = normalize_lang(user.language)
        # Owned cars only — see the note above.
        for car in list_owned_cars(db, user):
            text = build_weekly_digest(db, car, today=today, lang=lang)
            if text is not None:
                digests.append(WeeklyDigest(car=car, text=text))
        if digests:
            targets.append((user, digests))
    return targets


def set_digest_enabled(db: Session, user: User, enabled: bool) -> None:
    user.digest_enabled = enabled
    db.commit()
