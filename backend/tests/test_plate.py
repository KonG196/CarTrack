"""Plate/VIN lookup. The real service is never called: the free tier is ~1000
lookups a month for the whole instance, and a test suite would eat it."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import plate

# Trimmed from a real answer for VIN WVWZZZAUZHP541983 — the seeded Golf.
GOLF_PAYLOAD = {
    "digits": "AA1234BB",
    "vin": "WVWZZZAUZHP541983",
    "vendor": "Volkswagen",
    "model": "GOLF",
    "model_year": 2016,
    "photo_url": "https://baza-gai.com.ua/catalog-images/volkswagen/golf/image.jpg",
    "is_stolen": False,
    "stolen_details": None,
    "operations": [
        {
            "registered_at": "03.12.2022",
            "displacement": 1598,
            "color": {"ua": "Сірий"},
            "fuel": {"ua": "ДИЗЕЛЬНЕ ПАЛИВО"},
        },
        {"registered_at": "19.10.2022", "displacement": 1598},
    ],
}


@pytest.fixture
def key_on(monkeypatch):
    monkeypatch.setattr(settings, "BAZA_GAI_API_KEY", "test-key")


def _stub(monkeypatch, *, status_code=200, payload=None):
    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(status_code, json=payload or {}, request=request)

    monkeypatch.setattr(plate.httpx, "get", fake_get)


def test_disabled_without_a_key(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/plate/lookup", json={"query": "AA1234BB"}, headers=auth_headers
    )
    assert response.status_code == 503


def test_lookup_shapes_the_answer_into_car_fields(
    client: TestClient, auth_headers: dict, monkeypatch, key_on
) -> None:
    _stub(monkeypatch, payload=GOLF_PAYLOAD)
    response = client.post(
        "/api/plate/lookup", json={"query": "AA 1234 BB"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["brand"] == "Volkswagen"
    # Shouted in the register, readable here.
    assert body["model"] == "Golf"
    assert body["year"] == 2016
    assert body["vin"] == "WVWZZZAUZHP541983"
    assert body["fuel_type"] == "diesel"
    assert body["engine"] == "1.6"
    assert body["color"] == "Сірий"
    assert body["is_stolen"] is False
    assert body["registrations"] == 2
    assert body["last_registered_at"] == "03.12.2022"


def test_unknown_plate_is_404(
    client: TestClient, auth_headers: dict, monkeypatch, key_on
) -> None:
    _stub(monkeypatch, status_code=404, payload={"error": "not found"})
    response = client.post(
        "/api/plate/lookup", json={"query": "XX9999XX"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_rejected_key_surfaces_as_502_not_500(
    client: TestClient, auth_headers: dict, monkeypatch, key_on
) -> None:
    _stub(monkeypatch, status_code=401)
    response = client.post(
        "/api/plate/lookup", json={"query": "AA1234BB"}, headers=auth_headers
    )
    assert response.status_code == 502


def test_network_failure_surfaces_as_502(
    client: TestClient, auth_headers: dict, monkeypatch, key_on
) -> None:
    def boom(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(plate.httpx, "get", boom)
    response = client.post(
        "/api/plate/lookup", json={"query": "AA1234BB"}, headers=auth_headers
    )
    assert response.status_code == 502


def test_lookup_requires_auth(client: TestClient) -> None:
    assert client.post("/api/plate/lookup", json={"query": "AA1234BB"}).status_code == 401


def test_rate_limited_per_user(
    client: TestClient, auth_headers: dict, monkeypatch, key_on
) -> None:
    """One user must not be able to spend the monthly quota in an afternoon."""
    _stub(monkeypatch, payload=GOLF_PAYLOAD)
    codes = [
        client.post(
            "/api/plate/lookup", json={"query": "AA1234BB"}, headers=auth_headers
        ).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AA 1234 BB", "AA1234BB"),
        ("aa1234bb", "AA1234BB"),
        ("АА1234ВВ", "АА1234ВВ"),
        ("AA-1234-BB", "AA1234BB"),
    ],
)
def test_plate_normalisation(raw: str, expected: str) -> None:
    assert plate.normalize_plate(raw) == expected


def test_unknown_fuel_stays_empty() -> None:
    """Guessing a car's fuel wrong is worse than leaving the field alone."""
    payload = dict(GOLF_PAYLOAD, operations=[{"fuel": {"ua": "ВОДЕНЬ"}}])
    assert plate._shape(payload)["fuel_type"] is None
    assert plate._shape(payload)["fuel_label"] == "ВОДЕНЬ"
