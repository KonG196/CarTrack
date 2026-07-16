"""Ballpark costs: priced for the car in front of them, never impersonating history."""

import datetime as dt
from decimal import Decimal

from app.models import Car, CarSpec, LogEntry, MaintenanceDetails
from app.services.baseline_costs import (
    CarProfile,
    baseline_cost,
    baseline_for,
    oil_litres_for,
    parse_displacement,
    parse_spec_litres,
)
from app.services.forecast import car_profile, estimate_interval_cost
from app.services.presets import MAINTENANCE_PRESETS

GOLF = CarProfile(fuel_type="diesel", displacement_l=1.6, oil_litres=4.6)


def test_every_maintenance_preset_has_a_ballpark() -> None:
    """The presets are what «Створити типові інтервали» makes, so they are the
    titles most cars will actually carry."""
    for preset in MAINTENANCE_PRESETS:
        assert baseline_cost(preset.title, GOLF) is not None, preset.title


def test_an_oil_filter_is_not_priced_as_an_oil_change() -> None:
    """Both say «масл». One is a 600 ₴ filter and one is five litres of oil."""
    assert baseline_cost("Масляний фільтр", GOLF) == 700
    assert baseline_cost("Фільтр масляний ЦБ012317", GOLF) == 700
    assert baseline_cost("Олива двигуна", GOLF) > 3000


def test_a_bigger_engine_costs_more_to_service() -> None:
    """Volume is most of an oil change, and volume scales with the engine. One
    number for every car is what made this dumb."""
    small = baseline_cost("Олива двигуна", CarProfile(fuel_type="petrol", displacement_l=1.0))
    golf = baseline_cost("Олива двигуна", GOLF)
    v8 = baseline_cost("Олива двигуна", CarProfile(fuel_type="petrol", displacement_l=5.0))
    assert small < golf < v8


def test_the_owners_own_spec_sheet_wins() -> None:
    """«Олива двигуна: ~4.6 л» is transcribed from a service passport. Nothing
    derived beats a recorded fact."""
    recorded = CarProfile(fuel_type="diesel", displacement_l=2.0, oil_litres=4.6)
    assert oil_litres_for(recorded) == 4.6
    derived = CarProfile(fuel_type="diesel", displacement_l=2.0)
    assert oil_litres_for(derived) != 4.6


def test_the_derivation_lands_near_real_engines_without_pretending_to_hit_them() -> None:
    """Fitted over six real capacities, and it is within about a litre of each.

    It cannot do better: a 2.0 TDI takes 4.3 л and a 2.0 TSI takes 5.7, so the
    same displacement has two right answers. Asserting an exact match on one
    engine would be fitting the test to the formula.
    """
    for displacement, real in ((1.0, 4.0), (1.5, 3.75), (1.6, 4.6), (2.0, 4.3), (3.0, 7.9)):
        derived = oil_litres_for(CarProfile(displacement_l=displacement))
        assert abs(derived - real) <= 1.2, (displacement, derived, real)


def test_an_electric_car_does_not_change_its_oil() -> None:
    """Quoting a Tesla owner 3500 ₴ for an oil change is not a ballpark, it is
    nonsense with a currency sign."""
    tesla = CarProfile(fuel_type="electric")
    assert baseline_cost("Олива двигуна", tesla) is None
    assert baseline_cost("Паливний фільтр", tesla) is None
    assert baseline_cost("ГРМ", tesla) is None
    assert baseline_cost("Свічки запалювання", tesla) is None
    # It still has brakes and a cabin.
    assert baseline_cost("Гальмівна рідина", tesla) == 1150
    assert baseline_cost("Салонний фільтр", tesla) == 900


def test_a_diesel_has_no_spark_plugs_but_a_dear_fuel_filter() -> None:
    petrol = CarProfile(fuel_type="petrol", displacement_l=1.6)
    assert baseline_cost("Свічки запалювання", GOLF) is None
    assert baseline_cost("Свічки запалювання", petrol) == 1600
    assert baseline_cost("Паливний фільтр", GOLF) > baseline_cost("Паливний фільтр", petrol)


def test_a_car_we_know_nothing_about_still_gets_a_number() -> None:
    """A car added in ten seconds has a fuel type and little else."""
    assert baseline_cost("Олива двигуна", CarProfile()) is not None
    assert baseline_cost("Олива двигуна", None) is not None
    assert baseline_cost("Свічки запалювання", CarProfile()) == 1600


def test_what_it_does_not_know_it_does_not_guess() -> None:
    """A policy costs 2100-10000 ₴ depending on region and driver; a tax on a
    2016 Golf is 0 ₴. A ballpark for either is a wrong number, not a hint."""
    assert baseline_cost("Поліс ОСЦПВ", GOLF) is None
    assert baseline_cost("Транспортний податок", GOLF) is None
    assert baseline_cost("Зелена карта", GOLF) is None
    assert baseline_cost("Щось своє вигадане", GOLF) is None
    assert baseline_cost("", GOLF) is None


def test_a_ballpark_can_be_argued_with() -> None:
    for title in ("Олива двигуна", "ГРМ", "Гальмівна рідина"):
        assert baseline_for(title).made_of


def test_reads_the_engine_field_as_people_actually_write_it() -> None:
    assert parse_displacement("1.6 TDI") == 1.6
    assert parse_displacement("2,0 TSI") == 2.0
    assert parse_displacement("1598 см3") == 1.6
    assert parse_displacement("1.6 TDI CXXB") == 1.6
    # Not an engine: a year, a power figure, an empty field.
    assert parse_displacement("TDI") is None
    assert parse_displacement("") is None
    assert parse_displacement(None) is None


def test_reads_the_oil_volume_off_a_spec_sheet() -> None:
    assert parse_spec_litres("~4.6 л") == 4.6
    assert parse_spec_litres("4,6 л") == 4.6
    assert parse_spec_litres("VW 507.00") is None
    assert parse_spec_litres(None) is None
    # Not a sump: a 60-litre tank cannot be the oil.
    assert parse_spec_litres("60 л") is None


def test_the_profile_is_built_from_the_real_golf() -> None:
    car = Car(
        brand="Volkswagen",
        model="Golf VII Variant",
        engine="1.6 TDI",
        year=2016,
        fuel_type="diesel",
        current_odometer=240054,
    )
    car.specs = [CarSpec(category="Рідини та обʼєми", name="Олива двигуна", value="~4.6 л")]
    profile = car_profile(car)
    assert profile.fuel_type == "diesel"
    assert profile.displacement_l == 1.6
    assert profile.oil_litres == 4.6


def _service_log(item: str, cost: float, day: int) -> LogEntry:
    log = LogEntry(
        type="maintenance",
        odometer=200000 + day,
        date=dt.date(2026, 1, day),
        total_cost=Decimal(str(cost)),
    )
    log.maintenance = MaintenanceDetails(
        parts_cost=Decimal("0"), labor_cost=Decimal("0"), items=[item]
    )
    return log


def test_history_beats_the_market() -> None:
    """This car's own bills know the shop and the city. The table knows neither."""
    logs = [_service_log("Олива двигуна", 5600, 1), _service_log("Олива двигуна", 5600, 2)]
    estimate = estimate_interval_cost("Олива двигуна", logs)
    assert estimate.amount == 5600
    assert estimate.source == "history"


def test_the_market_fills_in_only_where_history_is_silent() -> None:
    logs = [_service_log("Олива двигуна", 5600, 1)]
    estimate = estimate_interval_cost("Гальмівна рідина", logs)
    assert estimate.amount == 1150
    assert estimate.source == "baseline"


def test_a_first_service_gets_a_number_instead_of_a_zero() -> None:
    estimate = estimate_interval_cost("Олива двигуна", [])
    assert estimate.amount > 0
    assert estimate.source == "baseline"


def test_an_unknown_interval_stays_empty_rather_than_invented() -> None:
    assert estimate_interval_cost("Поліс ОСЦПВ", []) is None
