"""Log photo tests: upload, streaming, deletion, ownership, disk side effects."""

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.models import LogPhoto

TODAY = dt.date.today()
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(target))
    return target


def _make_log(client: TestClient, headers: dict, car_id: int) -> dict:
    response = client.post(
        f"/api/cars/{car_id}/logs",
        json={
            "type": "expense",
            "odometer": 10100,
            "date": TODAY.isoformat(),
            "total_cost": 25,
            "notes": "мийка",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(
    client: TestClient,
    headers: dict,
    log_id: int,
    content: bytes = JPEG_BYTES,
    content_type: str = "image/jpeg",
    filename: str = "receipt.jpg",
):
    return client.post(
        f"/api/logs/{log_id}/photos",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


def test_upload_photo_creates_row_and_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])

    response = _upload(client, auth_headers, log["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == "image/jpeg"
    assert body["size"] == len(JPEG_BYTES)
    assert body["filename"].endswith(".jpg")
    assert "created_at" in body

    stored = list(uploads_dir.rglob(body["filename"]))
    assert len(stored) == 1
    assert stored[0].read_bytes() == JPEG_BYTES


def test_log_list_includes_photos(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.status_code == 200
    (item,) = listed.json()["items"]
    assert [p["id"] for p in item["photos"]] == [photo["id"]]


def test_get_photo_streams_the_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()

    response = client.get(f"/api/photos/{photo['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    assert response.headers["content-type"] == "image/jpeg"


def test_foreign_user_gets_404_everywhere(
    client: TestClient, auth_headers: dict, make_car, make_user, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()

    other_headers = make_user(email="intruder@example.com")
    assert _upload(client, other_headers, log["id"]).status_code == 404
    assert (
        client.get(f"/api/photos/{photo['id']}", headers=other_headers).status_code
        == 404
    )
    assert (
        client.delete(f"/api/photos/{photo['id']}", headers=other_headers).status_code
        == 404
    )


def test_upload_to_missing_log_404(
    client: TestClient, auth_headers: dict, uploads_dir: Path
) -> None:
    assert _upload(client, auth_headers, 12345).status_code == 404


def test_non_image_upload_415(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    response = _upload(
        client,
        auth_headers,
        log["id"],
        content=b"not an image",
        content_type="text/plain",
        filename="notes.txt",
    )
    assert response.status_code == 415


def test_oversized_upload_413(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    response = _upload(
        client, auth_headers, log["id"], content=b"x" * (10 * 1024 * 1024 + 1)
    )
    assert response.status_code == 413
    assert not list(uploads_dir.rglob("*.jpg"))


def test_delete_photo_removes_row_and_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()
    (stored,) = list(uploads_dir.rglob(photo["filename"]))

    response = client.delete(f"/api/photos/{photo['id']}", headers=auth_headers)
    assert response.status_code == 204
    assert not stored.exists()
    assert (
        client.get(f"/api/photos/{photo['id']}", headers=auth_headers).status_code
        == 404
    )


def test_delete_photo_survives_missing_file(
    client: TestClient, auth_headers: dict, make_car, uploads_dir: Path
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()
    (stored,) = list(uploads_dir.rglob(photo["filename"]))
    stored.unlink()  # file vanished behind the API's back

    response = client.delete(f"/api/photos/{photo['id']}", headers=auth_headers)
    assert response.status_code == 204


def test_deleting_log_cascades_photo_rows(
    client: TestClient,
    auth_headers: dict,
    make_car,
    uploads_dir: Path,
    db_session_factory,
) -> None:
    car = make_car()
    log = _make_log(client, auth_headers, car["id"])
    photo = _upload(client, auth_headers, log["id"]).json()

    assert client.delete(f"/api/logs/{log['id']}", headers=auth_headers).status_code == 204
    assert (
        client.get(f"/api/photos/{photo['id']}", headers=auth_headers).status_code
        == 404
    )
    with db_session_factory() as db:
        assert db.execute(select(func.count(LogPhoto.id))).scalar_one() == 0
