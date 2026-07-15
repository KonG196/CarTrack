"""Pure parser tests: odometer numbers vs quick expense vs refuel messages."""

import pytest

from app.bot.parsers import parse_odometer, parse_quick_expense, parse_refuel


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("123456", 123456),
        ("  123456  ", 123456),
        ("1", 1),
        ("2000000", 2000000),
    ],
)
def test_parse_odometer_accepts_plain_integers(text: str, expected: int) -> None:
    assert parse_odometer(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "0",
        "2000001",
        "-5000",
        "123.45",
        "123,45",
        "123456 км",
        "мийка 300",
        "",
        "   ",
        "abc",
    ],
)
def test_parse_odometer_rejects_invalid_input(text: str) -> None:
    assert parse_odometer(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("мийка 300", ("мийка", 300.0)),
        ("омивайка 150.50", ("омивайка", 150.5)),
        ("омивайка 150,50", ("омивайка", 150.5)),
        ("заміна лампи H7 450", ("заміна лампи H7", 450.0)),
        ("  парковка 25  ", ("парковка", 25.0)),
    ],
)
def test_parse_quick_expense_accepts_title_plus_amount(
    text: str, expected: tuple[str, float]
) -> None:
    assert parse_quick_expense(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "300",  # a bare number is an odometer update, not an expense
        "150.50",
        "мийка 0",
        "мийка -300",
        "мийка",
        "мийка 300 грн",
        "",
        "just some words",
    ],
)
def test_parse_quick_expense_rejects_invalid_input(text: str) -> None:
    assert parse_quick_expense(text) is None


def test_bare_number_routes_to_odometer_not_expense() -> None:
    assert parse_odometer("300") == 300
    assert parse_quick_expense("300") is None


def test_number_then_word_is_neither_odometer_nor_expense() -> None:
    assert parse_odometer("300 мийка") is None
    assert parse_quick_expense("300 мийка") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # liters + total -> price per liter is derived
        (
            "заправка 45л 2500",
            {"liters": 45.0, "price_per_liter": 55.56, "total_cost": 2500.0},
        ),
        # the amount may come before the liters
        (
            "заправка 2500 45.5 л",
            {"liters": 45.5, "price_per_liter": 54.95, "total_cost": 2500.0},
        ),
        # liters + price per liter -> total is derived
        (
            "заправка 45л 55.99 грн/л",
            {"liters": 45.0, "price_per_liter": 55.99, "total_cost": 2519.55},
        ),
        (
            "заправка 45,5 л 2500 грн",
            {"liters": 45.5, "price_per_liter": 54.95, "total_cost": 2500.0},
        ),
        (
            "  ЗАПРАВКА 40Л 2200  ",
            {"liters": 40.0, "price_per_liter": 55.0, "total_cost": 2200.0},
        ),
        (
            "заправ 40л 2200",
            {"liters": 40.0, "price_per_liter": 55.0, "total_cost": 2200.0},
        ),
        (
            "заправився 40 l 2200",
            {"liters": 40.0, "price_per_liter": 55.0, "total_cost": 2200.0},
        ),
        (
            "заправка 50 л 54 грн./л",
            {"liters": 50.0, "price_per_liter": 54.0, "total_cost": 2700.0},
        ),
        # all three stated: nothing is recomputed, the discount is preserved
        (
            "заправка 45л 55.99 грн/л 2400",
            {"liters": 45.0, "price_per_liter": 55.99, "total_cost": 2400.0},
        ),
    ],
)
def test_parse_refuel_accepts_refuel_messages(text: str, expected: dict) -> None:
    assert parse_refuel(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "45л 2500",
        "мийка 300",
        "300",
        "",
        "   ",
        "заправка",  # no numbers at all
        "заправка 2500",  # no liters -> cannot split the money
        "заправка 45л",  # liters only -> neither total nor price
        "заправка 0л 2500",  # zero liters
        "заправка 45л 0",  # zero total
        "заправка 45л 0 грн/л",  # zero price
        "заправка 45л 2500 3000",  # ambiguous: two candidate totals
        "перезаправка 45л 2500",  # «заправ» must lead the message
    ],
)
def test_parse_refuel_rejects_invalid_input(text: str) -> None:
    assert parse_refuel(text) is None


def test_refuel_message_is_checked_before_quick_expense() -> None:
    # A refuel message also matches the "<title> <amount>" expense shape, so
    # the router must try parse_refuel first or refuels become expenses.
    text = "заправка 45л 2500"
    assert parse_refuel(text) is not None
    assert parse_quick_expense(text) == ("заправка 45л", 2500.0)


def test_refuel_without_liters_still_falls_back_to_a_quick_expense() -> None:
    assert parse_refuel("заправка 300") is None
    assert parse_quick_expense("заправка 300") == ("заправка", 300.0)


# The fallback hint: what the bot says when no parser recognizes a message


def test_fallback_hint_lists_every_shape_the_parsers_understand() -> None:
    """The hint is the only map users get, so it must match the parsers.

    Every example below is a message this module actually parses; if a parser
    stops accepting one, this test fails instead of the bot quietly promising
    something it no longer does.
    """
    from app.bot.handlers import UNKNOWN_TEXT

    assert parse_odometer("123456") == 123456
    assert "123456" in UNKNOWN_TEXT

    assert parse_quick_expense("мийка 300") == ("мийка", 300.0)
    assert "мийка 300" in UNKNOWN_TEXT

    assert parse_refuel("заправка 45л 2500") is not None
    assert "заправка 45л 2500" in UNKNOWN_TEXT

    # Not parser shapes, but the rest of what the bot accepts.
    for promised in ("фото", "/status", "/report", "/help"):
        assert promised in UNKNOWN_TEXT, promised
