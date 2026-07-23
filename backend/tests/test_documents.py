"""Document library tests: upload, streaming, ownership, and interval linking."""

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.models import CarDocument, ServiceInterval

TODAY = dt.date.today()
PDF_BYTES = b"%PDF-1.4 fake-pdf-body"
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(target))
    return target


def _upload(
    client: TestClient,
    headers: dict,
    car_id: int,
    content: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
    filename: str = "policy.pdf",
    kind: str = "insurance",
    title: str = "ОСЦПВ 2026",
    expires_at: str | None = None,
):
    data = {"kind": kind, "title": title}
    if expires_at is not None:
        data["expires_at"] = expires_at
    return client.post(
        f"/api/cars/{car_id}/documents",
        files={"file": (filename, content, content_type)},
        data=data,
        headers=headers,
    )


# Upload / read / delete


def test_upload_pdf_creates_row_and_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    response = _upload(client, auth_headers, car["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["car_id"] == car["id"]
    assert body["kind"] == "insurance"
    assert body["title"] == "ОСЦПВ 2026"
    assert body["content_type"] == "application/pdf"
    assert body["size"] == len(PDF_BYTES)
    assert body["filename"].endswith(".pdf")
    assert body["expires_at"] is None
    assert body["linked_interval_id"] is None

    stored = list(uploads_dir.rglob(body["filename"]))
    assert len(stored) == 1
    assert stored[0].read_bytes() == PDF_BYTES


def test_upload_jpg_is_accepted(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    response = _upload(
        client,
        auth_headers,
        car["id"],
        content=JPEG_BYTES,
        content_type="image/jpeg",
        filename="passport.jpg",
        kind="tech_passport",
        title="Техпаспорт",
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "image/jpeg"
    assert response.json()["filename"].endswith(".jpg")


def test_list_documents_returns_newest_first(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    first = _upload(client, auth_headers, car["id"], title="Перший").json()
    second = _upload(client, auth_headers, car["id"], title="Другий").json()

    response = client.get(f"/api/cars/{car['id']}/documents", headers=auth_headers)
    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [second["id"], first["id"]]


def test_get_document_streams_the_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    document = _upload(client, auth_headers, car["id"]).json()

    response = client.get(f"/api/documents/{document['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"


def test_delete_document_removes_row_and_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    document = _upload(client, auth_headers, car["id"]).json()
    (stored,) = list(uploads_dir.rglob(document["filename"]))

    assert client.delete(f"/api/documents/{document['id']}", headers=auth_headers).status_code == 204
    assert not stored.exists()
    assert client.get(f"/api/documents/{document['id']}", headers=auth_headers).status_code == 404


def test_delete_document_survives_missing_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    document = _upload(client, auth_headers, car["id"]).json()
    (stored,) = list(uploads_dir.rglob(document["filename"]))
    stored.unlink()  # file vanished behind the API's back

    assert client.delete(f"/api/documents/{document['id']}", headers=auth_headers).status_code == 204


def test_deleting_a_car_cascades_its_documents(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path, db_session_factory
) -> None:
    car = make_car()
    _upload(client, auth_headers, car["id"])

    assert client.delete(f"/api/cars/{car['id']}", headers=auth_headers).status_code == 204
    with db_session_factory() as db:
        assert db.execute(select(func.count(CarDocument.id))).scalar_one() == 0


# Ownership and input limits


def test_foreign_user_gets_404_everywhere(
    client: TestClient, auth_headers: dict, make_car, make_user, uploads_dir: Path
) -> None:
    car = make_car()
    document = _upload(client, auth_headers, car["id"]).json()
    other = make_user(email="intruder@example.com")

    assert _upload(client, other, car["id"]).status_code == 404
    assert client.get(f"/api/cars/{car['id']}/documents", headers=other).status_code == 404
    assert client.get(f"/api/documents/{document['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/documents/{document['id']}", headers=other).status_code == 404


def test_upload_to_missing_car_404(
    client: TestClient, auth_headers: dict, uploads_dir: Path
) -> None:
    assert _upload(client, auth_headers, 12345).status_code == 404


def test_unsupported_type_415(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    response = _upload(
        client,
        auth_headers,
        car["id"],
        content=b"kind regards",
        content_type="text/plain",
        filename="notes.txt",
    )
    assert response.status_code == 415


def test_oversized_upload_413(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    response = _upload(client, auth_headers, car["id"], content=b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert not list(uploads_dir.rglob("*.pdf"))


def test_unknown_kind_422(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    assert _upload(client, auth_headers, car["id"], kind="passport_of_the_realm").status_code == 422


# Interval linking — the point of the feature


@pytest.mark.parametrize("kind", ["insurance", "inspection"])
def test_expiring_document_creates_a_date_only_interval(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path, kind: str
) -> None:
    car = make_car()
    expires = TODAY + dt.timedelta(days=200)

    body = _upload(
        client, auth_headers, car["id"], kind=kind, title="ОСЦПВ 2026", expires_at=expires.isoformat()
    ).json()
    assert body["expires_at"] == expires.isoformat()
    assert body["linked_interval_id"] is not None

    intervals = client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json()
    (interval,) = intervals
    assert interval["id"] == body["linked_interval_id"]
    assert interval["title"] == "ОСЦПВ 2026 (документ)"
    assert interval["interval_days"] == 365
    assert interval["interval_km"] is None
    assert interval["last_odometer"] is None
    assert interval["last_date"] == (expires - dt.timedelta(days=365)).isoformat()
    # The whole point: the interval comes due exactly when the document expires,
    # so the ordinary 14-day warning fires two weeks before it lapses.
    assert interval["due_date"] == expires.isoformat()


def test_expiring_document_without_expiry_creates_no_interval(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    body = _upload(client, auth_headers, car["id"], kind="insurance").json()
    assert body["linked_interval_id"] is None
    assert client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json() == []


@pytest.mark.parametrize("kind", ["tech_passport", "invoice", "other"])
def test_non_expiring_kinds_never_link_an_interval(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path, kind: str
) -> None:
    """A receipt with a date on it is not a deadline: only policies expire."""
    car = make_car()
    body = _upload(
        client,
        auth_headers,
        car["id"],
        kind=kind,
        title="Рахунок",
        expires_at=(TODAY + dt.timedelta(days=30)).isoformat(),
    ).json()
    assert body["linked_interval_id"] is None
    assert client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json() == []


def test_deleting_the_document_removes_its_expiry_interval(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    """Deleting the document also removes the reminder it booked: a nudge for a
    document that no longer exists can't be actioned and would fire forever."""
    car = make_car()
    body = _upload(
        client,
        auth_headers,
        car["id"],
        kind="insurance",
        expires_at=(TODAY + dt.timedelta(days=200)).isoformat(),
    ).json()

    assert client.delete(f"/api/documents/{body['id']}", headers=auth_headers).status_code == 204

    intervals = client.get(f"/api/cars/{car['id']}/intervals", headers=auth_headers).json()
    assert intervals == []


def test_failed_upload_leaves_no_interval_behind(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path, db_session_factory
) -> None:
    car = make_car()
    response = _upload(
        client,
        auth_headers,
        car["id"],
        content=b"x" * (10 * 1024 * 1024 + 1),
        kind="insurance",
        expires_at=(TODAY + dt.timedelta(days=200)).isoformat(),
    )
    assert response.status_code == 413
    with db_session_factory() as db:
        assert db.execute(select(func.count(ServiceInterval.id))).scalar_one() == 0
        assert db.execute(select(func.count(CarDocument.id))).scalar_one() == 0
