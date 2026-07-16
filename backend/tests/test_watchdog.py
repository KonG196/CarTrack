"""Consumption watchdog: the >15%-over-own-baseline spike detector."""

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.bot import service
from app.models import Car, LogEntry, RefuelDetails, User
from app.services.fuel import FuelSegment, FuelStats, detect_consumption_spike

TODAY = dt.date.today()


def _seg(consumption: float, log_id: int) -> FuelSegment:
    return FuelSegment(
        date=dt.date(2026, 1, 1) + dt.timedelta(days=log_id),
        odometer=1000 + log_id * 500,
        distance_km=500,
        liters=30.0,
        consumption_l_100km=consumption,
        log_id=log_id,
        start_log_id=log_id - 1,
    )


def _stats(consumptions: list[float], kind: str = "diesel") -> dict[str, FuelStats]:
    history = [_seg(c, i + 1) for i, c in enumerate(consumptions)]
    return {
        kind: FuelStats(
            avg_consumption_l_100km=None,
            last_consumption_l_100km=None,
            avg_cost_per_km=None,
            history=history,
        )
    }


def test_no_spike_without_enough_history() -> None:
    # Three segments cannot both give a baseline and be the newcomer.
    assert detect_consumption_spike(_stats([5.0, 5.0, 5.0])) is None


def test_spike_detected_above_threshold() -> None:
    # Baseline median 5.0; latest 6.0 is +20%, over the +15% bar.
    spike = detect_consumption_spike(_stats([5.0, 5.0, 5.0, 5.0, 6.0]))
    assert spike is not None
    assert spike.fuel_kind == "diesel"
    assert spike.log_id == 5
    assert spike.baseline_l_100km == 5.0
    assert spike.pct_over == 20


def test_no_spike_within_threshold() -> None:
    # 5.5 over a 5.0 baseline is +10% — under the bar, no warning.
    assert detect_consumption_spike(_stats([5.0, 5.0, 5.0, 5.0, 5.5])) is None


def test_baseline_uses_only_recent_window() -> None:
    # The ancient 12.0 is outside the 5-segment window, so the baseline is the
    # recent 5.0s and the closing 6.0 still counts as a spike.
    spike = detect_consumption_spike(_stats([12.0, 5.0, 5.0, 5.0, 5.0, 5.0, 6.0]))
    assert spike is not None
    assert spike.baseline_l_100km == 5.0
    assert spike.log_id == 7


def test_each_fuel_judged_on_its_own_history() -> None:
    # Petrol is steady; gas spikes. Only the gas segment is flagged.
    stats = {
        **_stats([6.0, 6.0, 6.0, 6.0, 6.0], kind="petrol"),
        **_stats([8.0, 8.0, 8.0, 8.0, 10.0], kind="lpg"),
    }
    spike = detect_consumption_spike(stats)
    assert spike is not None
    assert spike.fuel_kind == "lpg"
    assert spike.pct_over == 25


def _add_refuel(
    db: Session, car_id: int, odometer: int, day: dt.date, liters: float
) -> LogEntry:
    log = LogEntry(
        car_id=car_id,
        type="refuel",
        odometer=odometer,
        date=day,
        total_cost=Decimal("100"),
    )
    db.add(log)
    db.flush()
    db.add(
        RefuelDetails(
            log_entry_id=log.id,
            liters=Decimal(str(liters)),
            price_per_liter=Decimal("50"),
            is_full_tank=True,
        )
    )
    return log


def _spiking_car(db: Session) -> Car:
    """A diesel owner whose 5 segments read 5,5,5,5,6 l/100km (the last a spike).

    Six full tanks, 500 km apart; the closing litres set each segment's rate
    (25 L → 5.0, 30 L → 6.0). Dates end today so the spike is fresh.
    """
    user = User(email="w@example.com", hashed_password="x", telegram_chat_id="99")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="Skoda",
        model="Octavia",
        year=2018,
        fuel_type="diesel",
        current_odometer=3500,
    )
    db.add(car)
    db.flush()
    litres = [25, 25, 25, 25, 25, 30]  # first anchors, rest close a segment
    for i, litre in enumerate(litres):
        _add_refuel(
            db,
            car.id,
            odometer=1000 + i * 500,
            day=TODAY - dt.timedelta(days=(len(litres) - 1 - i) * 3),
            liters=litre,
        )
    db.commit()
    return car


def test_alert_targeted_then_stamped_then_excluded(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        car = _spiking_car(db)

        targets = service.consumption_alert_targets(db, today=TODAY)
        assert len(targets) == 1
        _user, alert = targets[0]
        assert alert.car.id == car.id
        assert alert.spike.pct_over == 20

        service.stamp_consumption_alert(db, alert.car, alert.spike.log_id)
        # The same spike is not reported a second time.
        assert service.consumption_alert_targets(db, today=TODAY) == []


def test_stale_spike_is_not_alerted(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        car = _spiking_car(db)
        # A spike older than the recency window is history, not news.
        future = TODAY + dt.timedelta(days=service.CONSUMPTION_RECENT_DAYS + 5)
        assert service.consumption_alert_targets(db, today=future) == []
        assert car.consumption_alert_log_id is None


def test_no_alert_when_fuel_notifications_off(db_session_factory) -> None:
    with db_session_factory() as db:
        car = _spiking_car(db)
        user = db.get(User, car.user_id)
        user.notify_fuel = False
        db.commit()
        assert service.consumption_alert_targets(db, today=TODAY) == []
