"""Service-order parsing and the /api/ocr/scan-order endpoint.

The fixtures are real: the orders from the seeded Golf's service passport, as
an OCR pass would hand them over. The tesseract binary is never invoked — the
endpoint tests monkeypatch extract_text inside ocr_llm, where both the API and
the bot read photos.
"""

import pytest
from fastapi.testclient import TestClient

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
        lambda image_bytes: "А-95 Energy\n45.50 Л x 54.99\nСУМА 2502.05 ГРН",
    )
    reading = recognize_photo(b"img")
    assert reading.kind == "refuel"
    assert reading.receipt.liters == 45.5


def test_classifier_calls_an_order_an_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO)
    reading = recognize_photo(b"img")
    assert reading.kind == "work_order"
    assert reading.work_order.total_cost == 8223.38


def test_classifier_admits_when_it_cannot_tell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes: "щощо")
    assert recognize_photo(b"img").kind == "unreadable"


def test_the_photo_is_read_once_not_once_per_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of one ladder and two readers: a наряд must not cost two
    OCR passes, which is what a user feels as another 15 seconds."""
    calls = []
    monkeypatch.setattr(
        "app.services.ocr_llm.extract_text",
        lambda image_bytes: calls.append(1) or ALEX_SO,
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
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes: ALEX_SO)
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
    monkeypatch.setattr("app.services.ocr_llm.extract_text", lambda image_bytes: "щощо")
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
        lambda image_bytes: "Заміна оливи 500,00\nвід 03.12.2099\nРазом: 500,00",
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
