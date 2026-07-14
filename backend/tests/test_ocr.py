"""Receipt OCR: pure text parsing + the /api/ocr/scan endpoint.

The tesseract binary is never invoked: parsing is tested on canned receipt
texts and the endpoint tests monkeypatch extract_text.
"""

import pytest
from fastapi.testclient import TestClient
from pytesseract import TesseractNotFoundError

from app.services.ocr import parse_receipt_text

OKKO_RECEIPT = """\
ТОВ "ОККО-РІТЕЙЛ"
АЗК №4021, м. Київ
ЧЕК ФН 3000112233
А-95 Energy
45.50 Л x 54.99
СУМА 2502.05 ГРН
ГОТІВКА
12.05.2024 14:32
"""

WOG_RECEIPT = """\
WOG КАФЕ
АЗК м. Львів
Дизель 30,00 л
ДО СПЛАТИ: 1650,00
КАРТКА
25/12/2023
"""

UKRNAFTA_RECEIPT = """\
АЗС УКРНАФТА
Бензин А-92
ЦІНА: 52,49 грн/л
ОБ'ЄМ: 20,00 л
РАЗОМ: 1049,80
05-01-2026
"""

GARBAGE_TEXT = """\
Дякуємо за покупку!
Гарного дня та безпечної дороги
"""


def test_parse_okko_receipt_computes_price_from_liters_and_total() -> None:
    parsed = parse_receipt_text(OKKO_RECEIPT)
    assert parsed.liters == 45.5
    assert parsed.total_cost == 2502.05
    # exactly two of three were found -> price derived: 2502.05 / 45.5 = 54.99
    assert parsed.price_per_liter == 54.99
    assert parsed.date is not None and parsed.date.isoformat() == "2024-05-12"
    assert parsed.gas_station == "OKKO"


def test_parse_wog_receipt_with_do_splaty_and_decimal_commas() -> None:
    parsed = parse_receipt_text(WOG_RECEIPT)
    assert parsed.liters == 30.0
    assert parsed.total_cost == 1650.0
    assert parsed.price_per_liter == 55.0
    assert parsed.date is not None and parsed.date.isoformat() == "2023-12-25"
    assert parsed.gas_station == "WOG"


def test_parse_receipt_with_hrn_per_liter_price_line() -> None:
    parsed = parse_receipt_text(UKRNAFTA_RECEIPT)
    # all three values are on the receipt: nothing gets recomputed
    assert parsed.liters == 20.0
    assert parsed.price_per_liter == 52.49
    assert parsed.total_cost == 1049.8
    assert parsed.date is not None and parsed.date.isoformat() == "2026-01-05"
    assert parsed.gas_station == "УКРНАФТА"


def test_parse_garbage_text_returns_all_none() -> None:
    parsed = parse_receipt_text(GARBAGE_TEXT)
    assert parsed.liters is None
    assert parsed.price_per_liter is None
    assert parsed.total_cost is None
    assert parsed.date is None
    assert parsed.gas_station is None


def test_third_value_computed_total_from_liters_and_price() -> None:
    parsed = parse_receipt_text("А-95\n40.00 л\nЦІНА 55.00 грн/л")
    assert parsed.liters == 40.0
    assert parsed.price_per_liter == 55.0
    assert parsed.total_cost == 2200.0


def test_third_value_computed_price_from_total_and_liters() -> None:
    parsed = parse_receipt_text("10,00 л\nСУМА 555.00")
    assert parsed.liters == 10.0
    assert parsed.total_cost == 555.0
    assert parsed.price_per_liter == 55.5


def test_single_value_does_not_trigger_computation() -> None:
    parsed = parse_receipt_text("СУМА 100.00")
    assert parsed.total_cost == 100.0
    assert parsed.liters is None
    assert parsed.price_per_liter is None


def test_parse_total_with_space_thousands_separator() -> None:
    parsed = parse_receipt_text("СУМА 1 250.50 ГРН")
    assert parsed.total_cost == 1250.50


def test_parse_total_with_european_thousands_format() -> None:
    parsed = parse_receipt_text("ДО СПЛАТИ: 1.250,50")
    assert parsed.total_cost == 1250.50


def test_absurd_liters_value_rejected_by_sanity_cap() -> None:
    # OCR misreads (e.g. a coupon/serial number glued to "л") must not be
    # taken as liters; with only the price known nothing else is derived.
    parsed = parse_receipt_text("Талони 1000 л\nЦІНА 54.99 грн/л")
    assert parsed.liters is None
    assert parsed.price_per_liter == 54.99
    assert parsed.total_cost is None


def test_liters_falls_back_to_next_plausible_match() -> None:
    parsed = parse_receipt_text("Талон 5000 л\nВидано: 45.50 л\nСУМА 2502.05")
    assert parsed.liters == 45.5
    assert parsed.total_cost == 2502.05


def test_price_per_liter_on_total_line_not_taken_as_total() -> None:
    # OCR sometimes merges lines: the per-liter price (54.99) is larger than
    # the actual small-refuel total (40.00) and must not win.
    parsed = parse_receipt_text("СУМА 40.00 ГРН 54.99 ГРН/Л")
    assert parsed.total_cost == 40.0
    assert parsed.price_per_liter == 54.99


def test_change_line_never_used_as_total() -> None:
    parsed = parse_receipt_text("СУМА 650.00\nГОТІВКА 700.00\nРЕШТА 50.00")
    assert parsed.total_cost == 650.0


def test_inconsistent_triple_is_kept_not_recomputed() -> None:
    # all three present but 20 * 52.49 != 999: found values stay untouched
    parsed = parse_receipt_text("ОБ'ЄМ: 20,00 л\nЦІНА: 52,49 грн/л\nРАЗОМ: 999,00")
    assert parsed.liters == 20.0
    assert parsed.price_per_liter == 52.49
    assert parsed.total_cost == 999.0


def test_impossible_date_skipped_for_next_valid_date() -> None:
    parsed = parse_receipt_text("32.13.2024\n12.05.2024")
    assert parsed.date is not None and parsed.date.isoformat() == "2024-05-12"


def _post_scan(client: TestClient, headers: dict, **file_overrides) -> object:
    file = ("receipt.jpg", b"fake-image-bytes", "image/jpeg")
    if file_overrides:
        file = (
            file_overrides.get("name", file[0]),
            file_overrides.get("content", file[1]),
            file_overrides.get("content_type", file[2]),
        )
    return client.post("/api/ocr/scan", files={"file": file}, headers=headers)


def test_scan_endpoint_returns_parsed_fields(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.routers.ocr.extract_text", lambda image_bytes: OKKO_RECEIPT)
    response = _post_scan(client, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["liters"] == 45.5
    assert body["price_per_liter"] == 54.99
    assert body["total_cost"] == 2502.05
    assert body["date"] == "2024-05-12"
    assert body["gas_station"] == "OKKO"
    assert body["raw_text"] == OKKO_RECEIPT


def test_scan_endpoint_maps_missing_tesseract_to_503(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_not_found(image_bytes: bytes) -> str:
        raise TesseractNotFoundError()

    monkeypatch.setattr("app.routers.ocr.extract_text", raise_not_found)
    response = _post_scan(client, auth_headers)
    assert response.status_code == 503
    assert "brew install tesseract tesseract-lang" in response.json()["detail"]


def test_scan_endpoint_rejects_non_image_with_415(
    client: TestClient, auth_headers: dict
) -> None:
    response = _post_scan(
        client, auth_headers, name="notes.txt", content=b"hello", content_type="text/plain"
    )
    assert response.status_code == 415


def test_scan_endpoint_rejects_upload_without_image_content_type_with_415(
    client: TestClient, auth_headers: dict
) -> None:
    # extensionless filename: the client falls back to application/octet-stream,
    # i.e. no usable image content type is declared
    response = _post_scan(
        client,
        auth_headers,
        name="receipt",
        content=b"x",
        content_type="application/octet-stream",
    )
    assert response.status_code == 415


def test_scan_endpoint_rejects_oversize_image_with_413(
    client: TestClient, auth_headers: dict
) -> None:
    response = _post_scan(client, auth_headers, content=b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_scan_endpoint_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/ocr/scan", files={"file": ("receipt.jpg", b"x", "image/jpeg")}
    )
    assert response.status_code == 401
