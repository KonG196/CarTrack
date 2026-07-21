"""Free-text LLM intent parsing for the bot."""

import pytest

from app.bot import ai_intent


def test_refuel_fields_derive_the_missing_number() -> None:
    # litres + total -> price
    assert ai_intent.refuel_fields_from_intent(
        {"liters": 40, "total_cost": 2200, "gas_station": "ОККО"}
    ) == {"liters": 40.0, "price_per_liter": 55.0, "total_cost": 2200.0, "gas_station": "ОККО"}
    # litres + price -> total
    assert ai_intent.refuel_fields_from_intent({"liters": 40, "price_per_liter": 55})["total_cost"] == 2200.0
    # price + total -> litres
    assert ai_intent.refuel_fields_from_intent({"price_per_liter": 55, "total_cost": 2200})["liters"] == 40.0


def test_refuel_fields_need_at_least_two_numbers() -> None:
    assert ai_intent.refuel_fields_from_intent({"total_cost": 2200}) is None
    assert ai_intent.refuel_fields_from_intent({"gas_station": "WOG"}) is None


def test_refuel_fields_reject_nonpositive_and_bool() -> None:
    assert ai_intent.refuel_fields_from_intent({"liters": 0, "total_cost": 2200}) is None
    assert ai_intent.refuel_fields_from_intent({"liters": True, "total_cost": 2200}) is None


def test_refuel_fields_blank_station_becomes_none() -> None:
    fields = ai_intent.refuel_fields_from_intent({"liters": 40, "total_cost": 2200, "gas_station": "  "})
    assert fields["gas_station"] is None


def test_parse_message_intent_returns_supported_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai_intent, "ask_gemini_json_text", lambda _p: {"action": "refuel", "liters": 40, "total_cost": 2200}
    )
    intent = ai_intent.parse_message_intent("залив 40л на окко за 2200")
    assert intent["action"] == "refuel"


def test_parse_message_intent_drops_none_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_intent, "ask_gemini_json_text", lambda _p: {"action": "none"})
    assert ai_intent.parse_message_intent("привіт як справи") is None


def test_parse_message_intent_survives_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_intent, "ask_gemini_json_text", lambda _p: None)
    assert ai_intent.parse_message_intent("щось") is None
    monkeypatch.setattr(ai_intent, "ask_gemini_json_text", lambda _p: ["not", "a", "dict"])
    assert ai_intent.parse_message_intent("щось") is None
