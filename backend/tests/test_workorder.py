"""Service-order parsing and the /api/ocr/scan-order endpoint.

The fixtures are real: the orders from the seeded Golf's service passport, as
an OCR pass would hand them over. The tesseract binary is never invoked — the
endpoint tests monkeypatch extract_text inside ocr_llm, where both the API and
the bot read photos.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import ocr_llm
from app.services.ocr_llm import recognize_photo
from app.services.workorder import looks_like_work_order, parse_work_order

# «Алекс Со», Львів — наряд №А000033003, the car's first Ukrainian service.
ALEX_SO = """ТОВ "АЛЕКС СО"
Наряд-замовлення №А000033003 від 03.12.2022
Автомобіль: VW Golf VII Variant  Пробіг: 190011 км

№ п/п  Найменування            Кільк.  Ціна     Сума
1  Олива моторна 5W-30 5л      1      2255,00  2255,00
2  Фільтр масляний ЦБ012317    1       566,00   566,00
3  Фільтр паливний ЦБ002028    1      1738,00  1738,00
4  Фільтр повітряний Ц5002028  1      1249,00  1249,00
5  Фільтр салонний ЦБ115092    1      1138,00  1138,00
6  Рідина гальмівна 1л         1       432,00   432,00
7  Гвинт різьбовий М14         1       164,00   164,00

Запчастини та матеріали:            7542,00
Роботи:                              681,38
Разом до сплати:                    8223,38
"""

# The engine overhaul: a shop that prints no split at all.
GRM_ORDER = """СТО Алекс Со
Акт виконаних робіт від 17.03.2023
Заміна комплекту ГРМ (ремінь, ролики)   12000,00
Заміна водяної помпи                     4500,00
Ремінь поліклиновий 40125188             3300,00
Всього:                                 19800,00
"""


def test_reads_the_items_a_shop_listed() -> None:
    parsed = parse_work_order(ALEX_SO)
    assert "Олива моторна 5W-30 5л" in parsed.items
    assert "Фільтр масляний ЦБ012317" in parsed.items
    assert "Рідина гальмівна 1л" in parsed.items
    assert len(parsed.items) == 7


def test_splits_parts_from_labour_and_finds_the_bill() -> None:
    parsed = parse_work_order(ALEX_SO)
    assert parsed.parts_cost == 7542.00
    assert parsed.labor_cost == 681.38
    assert parsed.total_cost == 8223.38
    assert parsed.date == "2022-12-03"
    assert parsed.confident


def test_header_and_paperwork_are_not_work() -> None:
    """The car, the odometer and the order number are not things that were done."""
    parsed = parse_work_order(ALEX_SO)
    joined = " ".join(parsed.items).lower()
    assert "наряд" not in joined
    assert "автомобіль" not in joined
    assert "190011" not in joined
    assert "найменування" not in joined


def test_order_without_a_split_still_gives_the_bill() -> None:
    parsed = parse_work_order(GRM_ORDER)
    assert parsed.total_cost == 19800.00
    assert parsed.date == "2023-03-17"
    assert "Заміна комплекту ГРМ (ремінь, ролики)" in parsed.items
    assert len(parsed.items) == 3


def test_a_split_that_contradicts_the_bill_is_dropped_not_guessed() -> None:
    """Money in a service record is what the car is sold on: half-empty beats
    plausibly wrong."""
    text = """Запчастини: 5000,00
Роботи: 2000,00
Разом до сплати: 9500,00
Заміна оливи 1000,00
"""
    parsed = parse_work_order(text)
    assert parsed.total_cost == 9500.00
    assert parsed.parts_cost is None
    assert parsed.labor_cost is None


def test_missing_total_is_added_up_only_from_printed_halves() -> None:
    text = """Запчастини та матеріали: 3200,00
Роботи: 1500,00
Заміна оливи двигуна 500,00
"""
    parsed = parse_work_order(text)
    assert parsed.parts_cost == 3200.00
    assert parsed.labor_cost == 1500.00
    assert parsed.total_cost == 4700.00


def test_vat_line_is_not_the_bill() -> None:
    text = """Заміна оливи 1000,00
ПДВ 20%: 1644,68
Разом до сплати: 8223,38
"""
    parsed = parse_work_order(text)
    assert parsed.total_cost == 8223.38


def test_garbage_is_admitted_not_invented() -> None:
    parsed = parse_work_order("рщплдо\n\n???")
    assert parsed.items == []
    assert parsed.total_cost is None
    assert not parsed.confident


def test_empty_text() -> None:
    parsed = parse_work_order("")
    assert not parsed.confident
    assert parsed.raw_text == ""


# The one that matters: a verbatim OCR dump of a real invoice — рахунок-фактура
# №643 from ФОП Ростоцький for this Golf's injector work, read by OCR.space with
# isTable on. Every invented fixture above passed before this file existed, and
# this one failed on all three sums.
_REAL_INVOICE = (
    Path(__file__).parent / "fixtures" / "invoice_643_ocrspace_table.txt"
).read_text()


def test_real_invoice_sums_are_read_exactly() -> None:
    parsed = parse_work_order(_REAL_INVOICE)
    assert parsed.labor_cost == 16000.00
    assert parsed.parts_cost == 3200.00
    assert parsed.total_cost == 19200.00
    assert parsed.date == "2026-07-06"
    assert parsed.confident


def test_real_invoice_split_adds_up_to_the_bill() -> None:
    """The shop's own arithmetic, which is the strongest check there is."""
    parsed = parse_work_order(_REAL_INVOICE)
    assert parsed.parts_cost + parsed.labor_cost == parsed.total_cost


def test_the_same_word_means_labour_once_and_parts_once() -> None:
    """«Разом:» appears twice, identical, meaning 16 000 then 3 200. Only the
    heading above it says which — this is why the parser tracks sections."""
    parsed = parse_work_order(_REAL_INVOICE)
    assert _REAL_INVOICE.lower().count("разом:") == 2
    assert parsed.labor_cost != parsed.parts_cost


def test_real_invoice_items_are_work_not_the_letterhead() -> None:
    parsed = parse_work_order(_REAL_INVOICE)
    assert "Демонтаж-монтаж форсунок" in parsed.items
    assert "Діагностика" in parsed.items
    assert any("Фільтр палива" in item for item in parsed.items)
    joined = " ".join(parsed.items).lower()
    for stray in ("iban", "телефон", "єдрпоу", "загальна сума", "ростоцький"):
        assert stray not in joined


def test_the_room_the_photo_was_taken_in_is_not_a_service_item() -> None:
    """A laptop behind the paper put «164 files changed, 9921 insertions(+)»
    through OCR. It names something and carries numbers, which is the whole of
    the item test — only being outside a priced section keeps it out."""
    parsed = parse_work_order(_REAL_INVOICE)
    joined = " ".join(parsed.items).lower()
    for stray in ("insertions", "git diff", "shortstat", "console", "vault"):
        assert stray not in joined


def test_a_cyrillic_letter_where_a_digit_belongs() -> None:
    """OCR reads «3 200,00» as «З 200,00». Untranslated it is 200 hryvnia —
    a sixteenth of the real subtotal, and no error anywhere."""
    assert "З 200,00" in _REAL_INVOICE
    assert parse_work_order(_REAL_INVOICE).parts_cost == 3200.00


def test_an_invoice_is_recognised_as_a_service_order() -> None:
    assert looks_like_work_order(_REAL_INVOICE)


def test_a_work_order_is_recognisable_as_one() -> None:
    assert looks_like_work_order(ALEX_SO)
    assert looks_like_work_order(GRM_ORDER)


def test_a_fuel_receipt_is_not_a_work_order() -> None:
    """The trap this guard exists for: a receipt is also a table of names and
    sums ending in «ДО СПЛАТИ», so it parses as a perfectly confident наряд."""
    receipt = """WOG КАФЕ
АЗК м. Львів
Дизель 30,00 л
ДО СПЛАТИ: 1650,00
КАРТКА
"""
    assert parse_work_order(receipt).confident
    assert not looks_like_work_order(receipt)


def test_classifier_calls_a_receipt_a_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes, **kw: "А-95 Energy\n45.50 Л x 54.99\nСУМА 2502.05 ГРН",
    )
    reading = recognize_photo(b"img")
    assert reading.kind == "refuel"
    assert reading.receipt.liters == 45.5


def test_classifier_calls_an_order_an_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: ALEX_SO)
    reading = recognize_photo(b"img")
    assert reading.kind == "work_order"
    assert reading.work_order.total_cost == 8223.38


def test_classifier_admits_when_it_cannot_tell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: "щощо")
    assert recognize_photo(b"img").kind == "unreadable"


def test_the_photo_is_read_once_not_once_per_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of one ladder and two readers: a наряд must not cost two
    OCR passes, which is what a user feels as another 15 seconds."""
    calls = []
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes, **kw: calls.append(1) or ALEX_SO,
    )
    recognize_photo(b"img")
    assert len(calls) == 1


def _post_order(client: TestClient, headers: dict, content: bytes = b"fake-image"):
    return client.post(
        "/api/ocr/scan-order",
        files={"file": ("order.jpg", content, "image/jpeg")},
        headers=headers,
    )


def test_endpoint_returns_a_card_ready_to_save(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: ALEX_SO)
    response = _post_order(client, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_cost"] == 8223.38
    assert body["parts_cost"] == 7542.00
    assert body["labor_cost"] == 681.38
    assert body["date"] == "2022-12-03"
    assert body["confident"] is True
    assert len(body["items"]) == 7


def test_endpoint_admits_an_unreadable_photo_instead_of_inventing_one(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: "щощо")
    response = _post_order(client, auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["confident"] is False
    assert body["total_cost"] is None
    assert body["items"] == []


def test_endpoint_drops_a_date_from_the_future(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No shop invoices work it has not done: «03.12.2099» is a misread year."""
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes, **kw: "Заміна оливи 500,00\nвід 03.12.2099\nРазом: 500,00",
    )
    response = _post_order(client, auth_headers)
    assert response.status_code == 200
    assert response.json()["date"] is None


def test_endpoint_rejects_a_non_image(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/ocr/scan-order",
        files={"file": ("order.pdf", b"%PDF-1.4", "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 415


def test_endpoint_rejects_an_oversize_image(client: TestClient, auth_headers: dict) -> None:
    response = _post_order(client, auth_headers, content=b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_endpoint_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/ocr/scan-order", files={"file": ("order.jpg", b"x", "image/jpeg")}
    )
    assert response.status_code == 401


# The vision rung: last, paid, and never trusted without checking


def test_the_model_reads_the_order_when_the_free_rungs_cannot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: "розмито")
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ocr_llm._ask_gemini",
        lambda prompt, image_bytes, content_type: {
            "parts_cost": 3200,
            "labor_cost": 16000,
            "total_cost": 19200,
            "date": "2026-07-06",
            "items": ["Демонтаж-монтаж форсунок", "Діагностика"],
        },
    )
    parsed = ocr_llm.recognize_work_order(b"img")
    assert parsed.total_cost == 19200
    assert parsed.labor_cost == 16000
    assert "Діагностика" in parsed.items


def test_the_model_is_asked_first_and_tesseract_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Vision-first: with a key the наряд goes straight to the model and the slow
    # tesseract pass is not run.
    def no_tesseract(*args, **kwargs):
        raise AssertionError("tesseract must not run on the vision-first path")

    monkeypatch.setattr("app.services.ocr_llm.extract_text", no_tesseract)
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ocr_llm._ask_gemini",
        lambda *args, **kwargs: {
            "parts_cost": 3200,
            "labor_cost": 5000,
            "total_cost": 8200,
            "date": None,
            "items": ["Робота"],
        },
    )
    assert ocr_llm.recognize_work_order(b"img").total_cost == 8200


def test_the_model_is_not_asked_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes, **kw: "розмито")
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "")

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the paid rung ran with no key configured")

    monkeypatch.setattr("app.services.ocr_llm._ask_gemini", must_not_be_called)
    assert not ocr_llm.recognize_work_order(b"img").confident


def test_a_model_split_that_does_not_add_up_is_dropped() -> None:
    """The same arithmetic the text parser is held to. A model cannot know which
    of the three it misread, so the halves go rather than the user trusting them."""
    parsed = ocr_llm.parsed_work_order_from_llm(
        {"parts_cost": 5000, "labor_cost": 2000, "total_cost": 9500, "items": ["Заміна оливи"]}
    )
    assert parsed.total_cost == 9500
    assert parsed.parts_cost is None
    assert parsed.labor_cost is None


def test_the_model_answering_nonsense_breaks_nothing() -> None:
    assert ocr_llm.parsed_work_order_from_llm("не json") is None
    assert ocr_llm.parsed_work_order_from_llm(None) is None
    empty = ocr_llm.parsed_work_order_from_llm({"items": None, "total_cost": "нуль"})
    assert empty.total_cost is None
    assert empty.items == []


def test_a_model_date_from_the_future_is_refused() -> None:
    parsed = ocr_llm.parsed_work_order_from_llm({"total_cost": 500, "date": "2099-01-01"})
    assert parsed.date is None


def test_the_model_survives_a_dead_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead/rate-limited key must not crash — it fast-fails to manual entry."""
    monkeypatch.setattr(ocr_llm.settings, "GEMINI_API_KEY", "dead-key")

    def boom(*args, **kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ocr_llm._ask_gemini", boom)
    parsed = ocr_llm.recognize_work_order(b"img")
    # Survives (no exception) and returns an empty reading for manual entry.
    assert parsed.total_cost is None
