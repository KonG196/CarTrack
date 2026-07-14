"""PDF report endpoint tests: headers, PDF validity and extracted content."""

import datetime as dt
import io

from fastapi.testclient import TestClient
from pypdf import PdfReader

TODAY = dt.date.today()


def _post_log(client: TestClient, headers: dict, car_id: int, payload: dict) -> None:
    response = client.post(f"/api/cars/{car_id}/logs", json=payload, headers=headers)
    assert response.status_code == 201, response.text


def _seed_mixed_logs(client: TestClient, headers: dict, car_id: int) -> None:
    """Seed one log of every type plus one service interval."""
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
