"""Receipt OCR: pure text parsing + the /api/ocr/scan endpoint.

The tesseract binary is never invoked: parsing is tested on canned receipt
texts and the endpoint tests monkeypatch extract_text inside ocr_llm,
where both the API and the bot now read receipts.
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

# Fiscal-printer layout: the dispensing line is "quantity X unit-price" with
# no liters marker, the fuel name carries the gross amount, and the paid
# total (after discount) is smaller than quantity * price.
OKKO_FISCAL_RECEIPT = """\
ПП "ОККО-НАФТОПРОДУКТ"
АЗС, магазин № КВ51
ВІДПУСК ПММ ТРАНЗ. 2313
ПРК № 6 КРАН № 3 -> РЕЗЕРВУАР № 5
40,45 X 19,99
Бензин А-92-Євро5-Е5 808,60А
Знижка: 06,51% -52,64
ФОРМА ОПЛАТИ: ПЛАТ. КАРТ 755,96
СУМА, ГРН 755,96
ПДВ А=20,00% 125,99
ДАТА: 15-01-16 ЧАС: 18:39:16
"""

# Verbatim tesseract output (grayscale, --psm 6) for a real photo of the
# receipt above: Latin lookalikes inside Cyrillic words («KAPT»), the leading
# "7" of the «СУМА» amount misread as "1", stray glyphs everywhere. The
# card-payment line kept the correct amount, so consistency with
# liters * price must rescue the total.
OKKO_FISCAL_OCR_NOISY = """\
ППО"ОККО-НАФТОПРОДУКТ" =
ВІДПУСК ПММ 40 ТРАНЗ, 2313
ПРКОю 6 КРАН ю 3 -» РЕЗЕРВУАР mM 5
40,45 Х 19,99
Бензин А-92-Євро5-ЕБ 808, 604
Знижка: | 06,51Х -52,64
ФОРМА ОПЛАТИ: ПЛАТ. KAPT 755,96
СУМА, ГРН 155,96
ПДВ  A=20,00% 125,99
ДАТА: 15-01-16 8 ЧАС: 18:39:16
"""

# Verbatim tesseract output (grayscale, 4x upscale, median filter, --psm 6)
# for a 387x516 thumbnail photo of an OKKO-СХІД receipt. True values:
# 64,84 л х 26,49 = 1717,61, discount 194,52, paid 1523,09. The liters
# digit is misread (54.84), «л» came out as "a", and every total keyword
# («СУМА», «ЕКВАЙРИНГ») is garbled — recovery must lean on the fuel-line
# gross amount and arithmetic consistency.
OKKO_THUMBNAIL_OCR = """\
TOR “OKKO-CXIL", ASC з магазмнок ККГЗ!
к, ERinpo, Вул, Набережна Перемоги, Зм
MH 37776071306
Касир 10
Таран 1.8.
NOX АТ Крам 52, Резервуар М
54.84 a x 26,49
Бензин &-95-£9905-E5 1717,61 5
Код; 9003 р
Зкихка, TPH. 194,9 D
СВ, ГА AR
Nas $=20, 00% 253,65
РВАРРИНІ 1523,09
TPH: 30001699992017082912351906
Paxywon Fishka: 12582194
Ічасник: Рожам lyanik
Баланс: 4.42 гри балами
Кор транс, 723512931789
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


def test_parse_okko_fiscal_receipt_qty_x_price_line() -> None:
    parsed = parse_receipt_text(OKKO_FISCAL_RECEIPT)
    assert parsed.liters == 40.45
    assert parsed.price_per_liter == 19.99
    # the paid (discounted) total wins, not liters * price = 808.60
    assert parsed.total_cost == 755.96
    assert parsed.gas_station == "OKKO"


def test_qty_x_price_with_cyrillic_separator() -> None:
    parsed = parse_receipt_text("ВІДПУСК ПММ\n38,10 х 54,49\nСУМА 2076,07")
    assert parsed.liters == 38.1
    assert parsed.price_per_liter == 54.49
    assert parsed.total_cost == 2076.07


def test_qty_x_price_skips_implausible_quantity() -> None:
    # a coupon/serial line with an "x" must not be taken for the fuel line
    parsed = parse_receipt_text("Талон 5000 x 1,00\n40,45 X 54,99")
    assert parsed.liters == 40.45
    assert parsed.price_per_liter == 54.99


def test_explicit_liters_marker_wins_over_qty_x_price_line() -> None:
    # shop items also print "qty x price"; the explicit "л" line is the fuel
    parsed = parse_receipt_text("Кава 2 x 35,00\nВидано: 45,50 л\nСУМА 2572,05")
    assert parsed.liters == 45.5
    assert parsed.total_cost == 2572.05


def test_noisy_fiscal_ocr_recovers_all_fields() -> None:
    parsed = parse_receipt_text(OKKO_FISCAL_OCR_NOISY)
    assert parsed.liters == 40.45
    assert parsed.price_per_liter == 19.99
    # 155.96 from the misread «СУМА» line is far from 40.45 * 19.99 = 808.60;
    # the card-payment amount 755.96 (gross minus the 52.64 discount) fits.
    assert parsed.total_cost == 755.96
    assert parsed.date is not None and parsed.date.isoformat() == "2016-01-15"
    assert parsed.gas_station == "OKKO"


def test_total_misread_rescued_by_liters_times_price_consistency() -> None:
    parsed = parse_receipt_text("40,45 X 19,99\nПЛАТ. КАРТ 755,96\nСУМА 155,96")
    assert parsed.total_cost == 755.96


def test_total_keyword_with_latin_lookalike_letters() -> None:
    # tesseract renders Cyrillic «СУМА» with Latin lookalikes: "CYMA"
    parsed = parse_receipt_text("CYMA 650.00")
    assert parsed.total_cost == 650.0


def test_two_digit_year_date_parsed_as_2000s() -> None:
    parsed = parse_receipt_text("ДАТА: 15-01-16 ЧАС: 18:39:16")
    assert parsed.date is not None and parsed.date.isoformat() == "2016-01-15"


def test_four_digit_year_wins_over_two_digit_year() -> None:
    parsed = parse_receipt_text("15-01-16\n12.05.2024")
    assert parsed.date is not None and parsed.date.isoformat() == "2024-05-12"


def test_future_two_digit_year_rejected() -> None:
    parsed = parse_receipt_text("ДАТА: 31-12-99")
    assert parsed.date is None


def test_thumbnail_ocr_recovers_fields_via_fuel_line_gross() -> None:
    parsed = parse_receipt_text(OKKO_THUMBNAIL_OCR)
    # 54.84 x 26,49 = 1452.71 appears nowhere in the text, while the fuel
    # line carries 1717,61 and 1717.61 / 26.49 divides cleanly to 64.84:
    # the quantity digit was the misread, so liters get repaired.
    assert parsed.liters == 64.84
    assert parsed.price_per_liter == 26.49
    # no total keyword survived; 1523,09 is the only amount in the
    # plausible band below the gross
    assert parsed.total_cost == 1523.09
    assert parsed.gas_station == "OKKO"


def test_price_from_x_line_when_liters_marker_also_present() -> None:
    # clean scan of the same receipt: liters come from the «л» marker and
    # the unit price must come from the same dispensing line (26,49), not
    # be derived from the discounted total (1523.09 / 64.84 = 23.49)
    parsed = parse_receipt_text("64,84 л х 26,49\nСУМА, ГРН. 1523,09")
    assert parsed.liters == 64.84
    assert parsed.price_per_liter == 26.49
    assert parsed.total_cost == 1523.09


def test_liters_repaired_when_product_with_price_not_in_text() -> None:
    parsed = parse_receipt_text(
        "54,84 л х 26,49\n"
        "Бензин А-95-Євро5-Е5 1717,61 Б\n"
        "ЕКВАЙРИНГ 1523,09\n"
        "Дата 23.08.2017"
    )
    assert parsed.liters == 64.84
    assert parsed.price_per_liter == 26.49
    assert parsed.total_cost == 1523.09
    assert parsed.date is not None and parsed.date.isoformat() == "2017-08-23"


def test_liters_kept_when_product_with_price_appears_in_text() -> None:
    # liters * price is printed on the receipt: the parsed quantity is
    # confirmed and the fuel-line amount is left alone even if it disagrees
    parsed = parse_receipt_text(
        "40,45 X 19,99\nБензин А-92-Євро5-ЕБ 808, 604\nСУМА, ГРН 755,96"
    )
    assert parsed.liters == 40.45
    assert parsed.price_per_liter == 19.99


def test_clean_lpg_receipt_with_tax_info_lines() -> None:
    # tax-info lines also say "грн/л" (per-liter tax) and "сплачено"; the
    # real price must come from the dispensing line, the real total from
    # «СУМА», and the tax lines must be ignored
    parsed = parse_receipt_text(
        "ПРК №8,Кран №2, Резервуар №6\n"
        "43,06 л х 15,99\n"
        "2711129700#АвтоГАЗ скраплений 688,53 Б\n"
        "СУМА, ГРН. 688,53\n"
        "ПДВ Б=20,00% 114,76\n"
        "ЕКВАЙРИНГ 688,53\n"
        "ПЛАТИМО ПОДАТКИ РАЗОМ:\n"
        "з цієї заправки сплачено\n"
        "187.82 грн податків, що\n"
        "складає 8.36 грн/л\n"
    )
    assert parsed.liters == 43.06
    assert parsed.price_per_liter == 15.99
    assert parsed.total_cost == 688.53


def test_implausible_price_per_liter_rejected() -> None:
    # "0.3 грн/л" / "3 грн/Л" are discount and tax rates, not fuel prices
    parsed = parse_receipt_text("знижка 0.3 грн/л\nСУМА 100.00")
    assert parsed.price_per_liter is None
    assert parsed.total_cost == 100.0


def test_tiny_amount_on_paid_line_not_taken_as_total() -> None:
    # garbled OCR of a tax line ("з заправки сплачено 4a") must not
    # produce a 4-hryvnia refuel
    parsed = parse_receipt_text("з заправки сплачено 4a")
    assert parsed.total_cost is None


def test_tax_summary_line_excluded_from_total() -> None:
    # «ПЛАТИМО ПОДАТКИ РАЗОМ» contains the total keyword «разом» but the
    # amount on it is taxes, not the receipt total
    parsed = parse_receipt_text("ПЛАТИМО ПОДАТКИ РАЗОМ: 187.82")
    assert parsed.total_cost is None


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
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes: OKKO_RECEIPT)
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

    monkeypatch.setattr("app.services.ocr_llm.extract_text", raise_not_found)
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
