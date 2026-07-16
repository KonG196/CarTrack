"""LPG savings: gas kilometres priced against petrol, from the car's own rates."""

import datetime as dt

from app.services.fuel import FuelSegment, FuelStats
from app.services.stats import compute_lpg_savings


def _stats(cost_per_km: float | None, segment_distances: list[int]) -> FuelStats:
    history = [
        FuelSegment(
            date=dt.date(2026, 1, i + 1),
            odometer=1000 + i * 500,
            distance_km=distance,
            liters=30.0,
            consumption_l_100km=8.0,
            log_id=i + 1,
        )
        for i, distance in enumerate(segment_distances)
    ]
    return FuelStats(
        avg_consumption_l_100km=8.0,
        last_consumption_l_100km=8.0,
        avg_cost_per_km=cost_per_km,
        history=history,
    )


def test_savings_computed_when_gas_is_cheaper() -> None:
    per_kind = {
        "petrol": _stats(3.0, [500]),
        "lpg": _stats(1.85, [500, 500]),  # 1000 km on gas
    }
    saved = compute_lpg_savings(per_kind)
    assert saved == {
        "gas_distance_km": 1000,
        "saved_per_km": 1.15,
        "saved_total": 1150.0,
    }


def test_no_savings_without_both_fuels() -> None:
    assert compute_lpg_savings({"petrol": _stats(3.0, [500])}) is None
    assert compute_lpg_savings({"lpg": _stats(1.85, [500])}) is None


def test_no_plaque_when_gas_not_cheaper() -> None:
    # Gas per-km >= petrol per-km: no saving to celebrate.
    per_kind = {
        "petrol": _stats(2.0, [500]),
        "lpg": _stats(2.2, [500]),
    }
    assert compute_lpg_savings(per_kind) is None
