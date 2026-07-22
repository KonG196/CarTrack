"""Gemini receipt-recognition fallback: JSON mapping + endpoint wiring.

No network calls: the mapper is tested on canned payloads, and the endpoint
tests monkeypatch recognize_receipt_llm / extract_text / settings inside
ocr_llm — the module that owns the ladder for both the API and the bot.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.services import ocr_llm
from app.services.ocr import ParsedReceipt
from app.services.ocr_llm import parsed_receipt_from_llm


def test_valid_payload_mapped_and_station_canonicalized() -> None:
    parsed = parsed_receipt_from_llm(
        {
            "liters": 43.06,
            "price_per_liter": 15.99,
            "total_cost": 688.53,
            "date": "2017-08-23",
            "gas_station": "АЗС ОККО-СХІД",
        }
    )
    assert parsed is not None
    assert parsed.liters == 43.06
    assert parsed.price_per_liter == 15.99
    assert parsed.total_cost == 688.53
    assert parsed.date == dt.date(2017, 8, 23)
    assert parsed.gas_station == "OKKO"
    assert parsed.found_in_text == 3


def test_comma_decimal_strings_accepted() -> None:
    parsed = parsed_receipt_from_llm({"liters": "43,06", "price_per_liter": "15,99"})
    assert parsed is not None
    assert parsed.liters == 43.06
    # exactly two known -> the third is derived, but does not count as found
    assert parsed.total_cost == 688.53
    assert parsed.found_in_text == 2


def test_implausible_values_dropped() -> None:
    parsed = parsed_receipt_from_llm(
        {"liters": 5000, "price_per_liter": 0.3, "total_cost": 4}
    )
    assert parsed is not None
    assert parsed.liters is None
    assert parsed.price_per_liter is None
    assert parsed.total_cost is None
    assert parsed.found_in_text == 0


def test_future_date_rejected() -> None:
    future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    parsed = parsed_receipt_from_llm({"date": future})
    assert parsed is not None
    assert parsed.date is None


def test_non_dict_payload_returns_none() -> None:
    assert parsed_receipt_from_llm(None) is None
    assert parsed_receipt_from_llm([1, 2]) is None


def test_transient_gemini_error_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.services import ocr_llm

    answer = {
        "candidates": [
            {"content": {"parts": [{"text": '{"liters": 43.06, "price_per_liter": 15.99}'}]}}
        ]
    }
    statuses = iter([503, 200])
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        return httpx.Response(
            next(statuses), json=answer, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(ocr_llm.httpx, "post", fake_post)
    monkeypatch.setattr(ocr_llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")
    parsed = ocr_llm.recognize_receipt_llm(b"img", "image/jpeg")
    assert calls["n"] == 2
    assert parsed is not None and parsed.liters == 43.06


def _post_scan(client: TestClient, headers: dict):
    return client.post(
        "/api/ocr/scan",
        files={"file": ("receipt.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )


def test_endpoint_falls_back_to_llm_when_tesseract_fails(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda b, **kw: "нечитабельно")
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ocr_llm.recognize_receipt_llm",
        lambda image_bytes, content_type, lang="en": ParsedReceipt(
            liters=43.06,
            price_per_liter=15.99,
            total_cost=688.53,
            gas_station="OKKO",
            found_in_text=3,
        ),
    )
    body = _post_scan(client, auth_headers).json()
    assert body["liters"] == 43.06
    assert body["price_per_liter"] == 15.99
    assert body["total_cost"] == 688.53
    assert body["gas_station"] == "OKKO"


def test_endpoint_returns_503_when_the_model_is_unavailable(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A vision-model failure is «scan unavailable» (503), not a bad photo — the
    # app maps 503 to «спробуйте пізніше» rather than «не вдалося розпізнати».
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")

    def boom(image_bytes: bytes, content_type: str, lang: str = "en") -> ParsedReceipt:
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ocr_llm.recognize_receipt_llm", boom)
    assert _post_scan(client, auth_headers).status_code == 503

    # Same when the model simply returns no answer (rate-limited / dead key).
    monkeypatch.setattr("app.services.ocr_llm.recognize_receipt_llm", lambda b, c, lang="en": None)
    assert _post_scan(client, auth_headers).status_code == 503


def test_llm_not_called_without_key(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda b, **kw: "нечитабельно")
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "")

    def must_not_be_called(image_bytes: bytes, content_type: str, lang: str = "en") -> ParsedReceipt:
        raise AssertionError("LLM fallback must stay disabled without a key")

    monkeypatch.setattr("app.services.ocr_llm.recognize_receipt_llm", must_not_be_called)
    assert _post_scan(client, auth_headers).status_code == 200


def test_model_reads_the_receipt_and_tesseract_is_skipped(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Vision-first: with a key the receipt goes straight to the model, and the
    # slow tesseract pass is not run at all.
    def no_tesseract(*args, **kwargs):
        raise AssertionError("tesseract must not run on the vision-first path")

    monkeypatch.setattr("app.services.ocr_llm.extract_text", no_tesseract)
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ocr_llm.recognize_receipt_llm",
        lambda image_bytes, content_type, lang="en": ocr_llm.parse_receipt_text(
            "45.50 Л x 54.99\nСУМА 2502.05 ГРН"
        ),
    )
    body = _post_scan(client, auth_headers).json()
    assert body["liters"] == 45.5
