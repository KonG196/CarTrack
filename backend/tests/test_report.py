"""PDF report endpoint tests: headers, PDF validity and extracted content."""

import datetime as dt
import io

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import event

TODAY = dt.date.today()


def _post_log(client: TestClient, headers: dict, car_id: int, payload: dict) -> None:
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text


def _seed_mixed_logs(client: TestClient, headers: dict, car_id: int) -> None:
    _post_log(
        client,
        headers,
        car_id,
        {
            "type": "maintenance",
            "odometer": 10100,
            "date": (TODAY - dt.timedelta(days=120)).isoformat(),
            "total_cost": 1500,
            "notes": "планове ТО",
            "maintenance": {
                "parts_cost": 1200,
                "labor_cost": 300,
                "items": ["Олива двигуна", "Масляний фільтр"],
            },
        },
    )
    _post_log(
        client,
        headers,
        car_id,
        {
            "type": "repair",
            "odometer": 10200,
            "date": (TODAY - dt.timedelta(days=60)).isoformat(),
            "total_cost": 2500,
            "repair": {"category": "Підвіска", "part_name": "Амортизатор"},
        },
    )
    _post_log(
        client,
        headers,
        car_id,
        {
            "type": "refuel",
            "odometer": 10300,
            "date": (TODAY - dt.timedelta(days=30)).isoformat(),
            "total_cost": 2475,
            "refuel": {"liters": 45, "price_per_liter": 55, "is_full_tank": True},
        },
    )
    _post_log(
        client,
        headers,
        car_id,
        {
            "type": "expense",
            "odometer": 10350,
            "date": (TODAY - dt.timedelta(days=10)).isoformat(),
            "total_cost": 300,
            "notes": "мийка",
        },
    )
    response = client.post(
        f"/api/cars/{car_id}/intervals",
        json={
            "title": "Заміна оливи двигуна",
            "interval_km": 10000,
            "interval_days": 365,
            "last_odometer": 10100,
            "last_date": (TODAY - dt.timedelta(days=120)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_report_returns_valid_pdf_with_content(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10350)
    _seed_mixed_logs(client, auth_headers, car["id"])

    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="kapot-tracker-report-{car["id"]}.pdf"'
    )
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 2048

    text = _extract_text(response.content)
    assert "Toyota" in text
    assert "Сервісна історія" in text
    assert "Олива двигуна" in text


def test_report_for_empty_car_is_still_valid_pdf(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

    text = _extract_text(response.content)
    assert "Kapot Tracker" in text
    assert "Записів поки немає" in text


def test_report_requires_ownership(client: TestClient, make_car, make_user) -> None:
    car = make_car()
    other_headers = make_user(email="other@example.com")
    response = client.get(f"/api/cars/{car['id']}/report", headers=other_headers)
    assert response.status_code == 404


def test_report_requires_auth(client: TestClient, make_car) -> None:
    car = make_car()
    assert client.get(f"/api/cars/{car['id']}/report").status_code == 401


# Real seeded note (382 chars, invoice numbers, « » quotes) from kapot_tracker.db.
SEEDED_LONG_NOTE = (
    "Профілактика нагару + ремонт ходової, наряд №А000193260, «Алекс Со» (Львів). "
    "Воднева чистка 3000; олива 2731.20; фільтр палив. 5Q0127177 — 1426.50; "
    "фільтр масл. 03N115562B — 438; сайлент-блок 5Q0407183L — 1570; роботи по "
    "ходовій (вісь, фланці, захист диска) ~2163. Сума з ПДВ. Повітряний і "
    "салонний фільтри замінені разом з оливою (за словами власника, в наряді "
    "окремо не виділені)."
)


def test_report_markup_like_user_text_does_not_crash(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """Notes/titles with <tag>-like text and & must render, not raise."""
    car = make_car(brand="Q&M <Motors>", current_odometer=10500)
    _post_log(
        client,
        auth_headers,
        car["id"],
        {
            "type": "repair",
            "odometer": 10400,
            "date": TODAY.isoformat(),
            "total_cost": 800,
            "notes": "заміна втулки <br> Bosch & Delphi <b>термінове",
            "repair": {"category": "Підвіска", "part_name": "Втулка <передня>"},
        },
    )
    response = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Фільтр <br> салона & двигуна", "interval_km": 15000, "last_odometer": 10000},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    text = _extract_text(response.content)
    assert "Bosch & Delphi" in text
    assert "Q&M <Motors>" in text


def test_report_emoji_in_notes_does_not_raise(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=10500)
    _post_log(
        client,
        auth_headers,
        car["id"],
        {
            "type": "repair",
            "odometer": 10400,
            "date": TODAY.isoformat(),
            "total_cost": 500,
            "notes": "Замінив оливу 🚗🔧 все ок 😀",
            "repair": {"category": "Двигун"},
        },
    )
    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_report_long_seeded_notes_wrap(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=240054)
    _post_log(
        client,
        auth_headers,
        car["id"],
        {
            "type": "maintenance",
            "odometer": 239000,
            "date": TODAY.isoformat(),
            "total_cost": 11328,
            "notes": SEEDED_LONG_NOTE,
            "maintenance": {"parts_cost": 9165, "labor_cost": 2163, "items": []},
        },
    )
    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200
    text = _extract_text(response.content)
    assert "А000193260" in text
    assert "5Q0407183L" in text


def test_report_with_hundreds_of_logs_paginates(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=60000)
    for i in range(205):
        _post_log(
            client,
            auth_headers,
            car["id"],
            {
                "type": "repair",
                "odometer": 10000 + i * 200,
                "date": (TODAY - dt.timedelta(days=410 - 2 * i)).isoformat(),
                "total_cost": 100 + i,
                "notes": f"запис №{i}",
                "repair": {"category": "Інше", "part_name": f"Деталь {i}"},
            },
        )
    response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
    assert response.status_code == 200

    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "запис №0" in text
    assert "запис №204" in text


def test_report_totals_match_analytics_totals(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The PDF must present the same totals the analytics endpoint reports."""
    car = make_car(current_odometer=10350)
    _seed_mixed_logs(client, auth_headers, car["id"])

    analytics = client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers)
    assert analytics.status_code == 200
    totals = analytics.json()["totals"]
    assert totals["all_time"] == 6775.0
    assert totals["by_type"]["refuel"] == 2475.0

    text = _extract_text(
        client.get(f"/api/cars/{car['id']}/report", headers=auth_headers).content
    )
    assert "6 775 грн" in text  # all-time total, analytics figure
    assert "2 475 грн" in text  # refuel total, analytics figure


def test_report_query_count_does_not_scale_with_logs(
    client: TestClient, auth_headers: dict, make_car, db_engine
) -> None:
    """Log detail rows must be eager-loaded, not lazy-loaded per log (N+1)."""
    counts: list[int] = []
    for n_logs in (2, 12):
        car = make_car(current_odometer=30000)
        for i in range(n_logs):
            payload = {
                "type": "repair" if i % 2 else "refuel",
                "odometer": 10000 + i * 100,
                "date": (TODAY - dt.timedelta(days=n_logs - i)).isoformat(),
                "total_cost": 500,
            }
            if payload["type"] == "repair":
                payload["repair"] = {"category": "Підвіска", "part_name": f"Деталь {i}"}
            else:
                payload["refuel"] = {"liters": 40, "price_per_liter": 55, "is_full_tank": True}
            _post_log(client, auth_headers, car["id"], payload)

        statements: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db_engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get(f"/api/cars/{car['id']}/report", headers=auth_headers)
        finally:
            event.remove(db_engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        counts.append(len(statements))

    assert counts[0] == counts[1], f"query count grew with log count: {counts}"
