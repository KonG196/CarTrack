"""Offline VIN decoder: normalization, WMI table, model year, API endpoint."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.services.vin import decode_vin, normalize_vin

# The owner's Golf VII Variant: a European VIN whose check digit is filler
# (the Z at position 9), which is exactly why we never verify it.
GOLF_VIN = "WVWZZZAUZHP541983"


# Normalization and validation (no check digit — European VINs omit it)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (GOLF_VIN, GOLF_VIN),
        (GOLF_VIN.lower(), GOLF_VIN),
        (f"  {GOLF_VIN}  ", GOLF_VIN),
        ("wvwzzzauzhp541983", GOLF_VIN),
    ],
)
def test_normalize_vin_upcases_and_strips(raw: str, expected: str) -> None:
    assert normalize_vin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        None,
        "WVWZZZAUZHP54198",  # 16 chars
        "WVWZZZAUZHP5419833",  # 18 chars
        "WVWZZZAUZHP54198I",  # I is not in the VIN alphabet
        "WVWZZZAUZHP54198O",  # O is not in the VIN alphabet
        "WVWZZZAUZHP54198Q",  # Q is not in the VIN alphabet
        "WVWZZZAUZHP54198-",
        "WVWZZZAUZHP 41983",
    ],
)
def test_normalize_vin_rejects_invalid_input(raw) -> None:
    assert normalize_vin(raw) is None


def test_check_digit_is_not_verified() -> None:
    """The Golf's 9th char is a filler Z: a check-digit test would reject it."""
    assert GOLF_VIN[8] == "Z"
    assert decode_vin(GOLF_VIN)["valid"] is True


# Decoding


def test_decode_golf_vin() -> None:
    assert decode_vin(GOLF_VIN) == {
        "wmi": "WVW",
        "manufacturer": "Volkswagen",
        "country": "Німеччина",
        "model_year": 2017,  # position 10 = H
        "valid": True,
    }


def test_decode_accepts_lowercase_and_padding() -> None:
    assert decode_vin(f" {GOLF_VIN.lower()} ") == decode_vin(GOLF_VIN)


@pytest.mark.parametrize(
    ("vin", "manufacturer", "country"),
    [
        ("WAUZZZ8V0HA000001", "Audi", "Німеччина"),
        ("WBA3B1C50HK000001", "BMW", "Німеччина"),
        ("WDB2030461A000001", "Mercedes-Benz", "Німеччина"),
        ("VF1RFA00567000001", "Renault", "Франція"),
        ("VF37ABCDE00000001", "Peugeot", "Франція"),
        ("TMBJJ7NE0H0000001", "Škoda", "Чехія"),
        ("ZFA31200000000001", "Fiat", "Італія"),
        ("JHMCM56557C000001", "Honda", "Японія"),
        ("KMHDU46D07U000001", "Hyundai", "Корея"),
        ("XTA210740A0000001", "АвтоВАЗ (LADA)", "Росія"),
        ("Y6DTF69Y0A0000001", "ЗАЗ", "Україна"),
    ],
)
def test_decode_known_wmi_prefixes(vin: str, manufacturer: str, country: str) -> None:
    decoded = decode_vin(vin)
    assert decoded["valid"] is True
    assert decoded["wmi"] == vin[:3]
    assert decoded["manufacturer"] == manufacturer
    assert decoded["country"] == country


@pytest.mark.parametrize(
    ("vin", "country"),
    [
        ("1FAFP40634F000001", "США"),
        ("2T1BR32E44C000001", "Канада"),
        ("3VWFE21C04M000001", "Мексика"),
        ("4T1BE32K24U000001", "США"),
        ("5NPE24AF4FH000001", "США"),
    ],
)
def test_decode_north_american_prefixes_give_country_only(vin: str, country: str) -> None:
    decoded = decode_vin(vin)
    assert decoded["valid"] is True
    assert decoded["country"] == country
    assert decoded["manufacturer"] is None


def test_decode_unknown_wmi_stays_valid_but_says_nothing() -> None:
    decoded = decode_vin("ABC12345678901234")
    assert decoded["valid"] is True
    assert decoded["wmi"] == "ABC"
    assert decoded["manufacturer"] is None
    assert decoded["country"] is None
    assert decoded["model_year"] == 2007  # position 10 = 7


@pytest.mark.parametrize("vin", ["", "   ", None, "WVWZZZAUZHP5419", "WVWZZZAUZHP54198I"])
def test_decode_invalid_vin_reports_nothing(vin) -> None:
    assert decode_vin(vin) == {
        "wmi": None,
        "manufacturer": None,
        "country": None,
        "model_year": None,
        "valid": False,
    }


# Model year (ISO 3779 position 10, 30-year cycle)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("H", 2017),  # the Golf
        ("A", 2010),
        ("Y", 2000),  # 2030 is beyond today+1 -> the older candidate wins
        ("1", 2001),  # 2031 is beyond today+1 -> the older candidate wins
        ("9", 2009),
        ("R", 2024),
        ("S", 2025),
        ("T", 2026),
        ("V", 2027),  # today + 1: still plausible, next model year
        ("W", 1998),  # 2028 is too far ahead -> 30 years back
    ],
)
def test_model_year_from_position_10(code: str, expected: int) -> None:
    # today is pinned: the 1980/2010 tie-break is defined against it, so the
    # boundary cases must not silently change meaning next January.
    vin = f"WVWZZZAUZ{code}P541983"
    assert len(vin) == 17
    assert decode_vin(vin, today=dt.date(2026, 7, 15))["model_year"] == expected


def test_model_year_zero_is_not_a_year_code() -> None:
    # 0 never appears in the year position of a real VIN.
    assert decode_vin("WVWZZZAUZ0P541983")["model_year"] is None


def test_model_year_is_resolved_against_today_not_a_hardcoded_year() -> None:
    future = dt.date(2036, 1, 1)
    # Code A: 2040 is beyond 2037 -> 2010.
    assert decode_vin("WVWZZZAUZAP541983", today=future)["model_year"] == 2010
    # Code H: 2047 is beyond 2037 -> 2017.
    assert decode_vin(GOLF_VIN, today=future)["model_year"] == 2017


# POST /api/vin/decode


def test_decode_endpoint_returns_the_decoder_result(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/vin/decode", json={"vin": GOLF_VIN.lower()}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "wmi": "WVW",
        "manufacturer": "Volkswagen",
        "country": "Німеччина",
        "model_year": 2017,
        "valid": True,
    }


def test_decode_endpoint_reports_an_invalid_vin_without_failing(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/api/vin/decode", json={"vin": "WVWZZZ"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is False
    assert response.json()["manufacturer"] is None


def test_decode_endpoint_requires_auth(client: TestClient) -> None:
    assert client.post("/api/vin/decode", json={"vin": GOLF_VIN}).status_code == 401


def test_decoder_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The decoder is an offline table: vPIC gives EU VINs nothing we lack.

    (An empirical check confirmed NHTSA vPIC fills only Make / Manufacturer /
    PlantCountry / ModelYear for European VINs — all of which the table below
    already reproduces, with no network and no extra dependency.)
    """
    import socket

    def _no_network(*args, **kwargs):
        raise AssertionError("the VIN decoder must not touch the network")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)

    assert decode_vin(GOLF_VIN)["manufacturer"] == "Volkswagen"
