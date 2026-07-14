"""Pure parser tests: odometer numbers vs quick expense messages."""

import pytest

from app.bot.parsers import parse_odometer, parse_quick_expense


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
    # "300 мийка" (amount before title) is deliberately unsupported: it is
    # not an odometer value and not a "<title> <amount>" expense, so the bot
    # answers with the usage hint instead of guessing.
    assert parse_odometer("300 мийка") is None
    assert parse_quick_expense("300 мийка") is None
