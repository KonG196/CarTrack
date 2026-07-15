"""The role × action access matrix — every car-scoped route, every role.

This file is the executable form of the permission table in the sharing
plan. Each endpoint declares the role it requires; the expected status is
then *derived*, not written down per case:

* a stranger always gets 404 — «not yours» never admits the car exists;
* enough rank gets the endpoint's ordinary success status;
* too little rank gets 403 — «yours, but you may not do that» is said plainly.

Adding a car-scoped route without adding it here is how an ownership hole
gets in, so the list below is meant to be exhaustive.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.access import (
    ROLE_RANK,
    get_accessible_car,
    list_accessible_cars,
    user_role_for_car,
)
from app.config import settings
from app.models import Car, CarDocument, CarMember, ObdSession, User
from app.services.photos import new_photo_filename, write_photo_file

TODAY = dt.date.today()
JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-body"

ROLES = ("owner", "editor", "viewer", "stranger")


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(target))
    return target


@pytest.fixture()
def world(client: TestClient, make_user, db_session_factory, uploads_dir: Path):
    """One owner with a fully furnished car: log, interval, spec, photo, obd, document."""
    owner_headers = make_user("owner@example.com")

    car = client.post(
        "/api/cars",
        json={
            "brand": "Volkswagen",
            "model": "Golf",
            "year": 2015,
            "fuel_type": "diesel",
            "current_odometer": 200_000,
        },
        headers=owner_headers,
    ).json()

    log = client.post(
        f"/api/cars/{car['id']}/logs",
        json={
            "type": "expense",
            "odometer": 200_100,
            "date": TODAY.isoformat(),
            "total_cost": 25,
            "notes": "мийка",
        },
        headers=owner_headers,
    ).json()

    interval = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Заміна мастила", "interval_km": 15000},
        headers=owner_headers,
    ).json()

    spec = client.post(
        f"/api/cars/{car['id']}/specs",
        json={"category": "Допуски", "name": "Мастило", "value": "VW 507.00"},
        headers=owner_headers,
    ).json()

    photo = client.post(
        f"/api/logs/{log['id']}/photos",
        files={"file": ("receipt.jpg", JPEG_BYTES, "image/jpeg")},
        headers=owner_headers,
    ).json()

    with db_session_factory() as db:
        owner = db.execute(
            select(User).where(User.email == "owner@example.com")
        ).scalar_one()
        obd_session = ObdSession(
            car_id=car["id"], filename="drive.csv", duration_s=60.0, sample_count=60
        )
        filename = new_photo_filename("policy.pdf", "application/pdf")
        document = CarDocument(
            car_id=car["id"],
            kind="insurance",
            title="ОСЦПВ",
            filename=filename,
            content_type="application/pdf",
            size=3,
        )
        db.add_all([obd_session, document])
        db.commit()
        # Documents live under the car owner's directory — see the storage
        # note in routers/documents.py.
        write_photo_file(owner.id, filename, b"pdf")
        ids = SimpleNamespace(
            owner_id=owner.id, obd_id=obd_session.id, document_id=document.id
        )

    return SimpleNamespace(
        owner_headers=owner_headers,
        owner_id=ids.owner_id,
        car_id=car["id"],
        log_id=log["id"],
        interval_id=interval["id"],
        spec_id=spec["id"],
        photo_id=photo["id"],
        obd_id=ids.obd_id,
        document_id=ids.document_id,
    )


@pytest.fixture()
def actor(client: TestClient, make_user, db_session_factory, world):

    def _actor(role: str) -> dict[str, str]:
        if role == "owner":
            return world.owner_headers
        email = f"{role}@example.com"
        headers = make_user(email)
        if role != "stranger":
            with db_session_factory() as db:
                user = db.execute(select(User).where(User.email == email)).scalar_one()
                db.add(CarMember(car_id=world.car_id, user_id=user.id, role=role))
                db.commit()
        return headers

    return _actor


# The matrix

# (label, min_role, status when allowed, request builder)
#
# A few builders deliberately send a payload the endpoint will reject: the
# access gate runs before payload parsing, so «allowed» there means 415/422
# rather than 2xx. That is the point — it proves the gate is not what failed.
ENDPOINTS: tuple[tuple, ...] = (
    # ---- read: viewer and up ------------------------------------------------
    ("GET car", "viewer", 200, lambda w: ("GET", f"/api/cars/{w.car_id}", {})),
    ("GET logs", "viewer", 200, lambda w: ("GET", f"/api/cars/{w.car_id}/logs", {})),
    ("GET log", "viewer", 200, lambda w: ("GET", f"/api/logs/{w.log_id}", {})),
    (
        "GET refuel-context",
        "viewer",
        200,
        lambda w: ("GET", f"/api/cars/{w.car_id}/refuel-context", {}),
    ),
    (
        "GET intervals",
        "viewer",
        200,
        lambda w: ("GET", f"/api/cars/{w.car_id}/intervals", {}),
    ),
    (
        "GET analytics",
        "viewer",
        200,
        lambda w: ("GET", f"/api/cars/{w.car_id}/analytics", {}),
    ),
    ("GET report", "viewer", 200, lambda w: ("GET", f"/api/cars/{w.car_id}/report", {})),
    (
        "GET export.csv",
        "viewer",
        200,
        lambda w: ("GET", f"/api/cars/{w.car_id}/export.csv", {}),
    ),
    ("GET specs", "viewer", 200, lambda w: ("GET", f"/api/cars/{w.car_id}/specs", {})),
    (
        "GET documents",
        "viewer",
        200,
        lambda w: ("GET", f"/api/cars/{w.car_id}/documents", {}),
    ),
    ("GET document", "viewer", 200, lambda w: ("GET", f"/api/documents/{w.document_id}", {})),
    ("GET obd list", "viewer", 200, lambda w: ("GET", f"/api/cars/{w.car_id}/obd", {})),
    ("GET obd session", "viewer", 200, lambda w: ("GET", f"/api/obd/{w.obd_id}", {})),
    ("GET photo", "viewer", 200, lambda w: ("GET", f"/api/photos/{w.photo_id}", {})),
    # ---- write: editor and up -----------------------------------------------
    (
        "POST log",
        "editor",
        201,
        lambda w: (
            "POST",
            f"/api/cars/{w.car_id}/logs",
            {
                "json": {
                    "type": "expense",
                    "odometer": 200_200,
                    "date": TODAY.isoformat(),
                    "total_cost": 10,
                }
            },
        ),
    ),
    (
        "PATCH log",
        "editor",
        200,
        lambda w: ("PATCH", f"/api/logs/{w.log_id}", {"json": {"total_cost": 30}}),
    ),
    ("DELETE log", "editor", 204, lambda w: ("DELETE", f"/api/logs/{w.log_id}", {})),
    (
        "POST photo",
        "editor",
        201,
        lambda w: (
            "POST",
            f"/api/logs/{w.log_id}/photos",
            {"files": {"file": ("x.jpg", JPEG_BYTES, "image/jpeg")}},
        ),
    ),
    ("DELETE photo", "editor", 204, lambda w: ("DELETE", f"/api/photos/{w.photo_id}", {})),
    (
        "POST interval complete",
        "editor",
        201,
        lambda w: (
            "POST",
            f"/api/intervals/{w.interval_id}/complete",
            {"json": {"odometer": 200_300, "date": TODAY.isoformat(), "total_cost": 50}},
        ),
    ),
    (
        # allowed → 422: access passes, the garbage CSV is what fails
        "POST obd",
        "editor",
        422,
        lambda w: (
            "POST",
            f"/api/cars/{w.car_id}/obd",
            {"files": {"file": ("drive.csv", b"not-a-csv", "text/csv")}},
        ),
    ),
    ("DELETE obd", "editor", 204, lambda w: ("DELETE", f"/api/obd/{w.obd_id}", {})),
    (
        # allowed → 415: access passes, the content type is what fails
        "POST document",
        "editor",
        415,
        lambda w: (
            "POST",
            f"/api/cars/{w.car_id}/documents",
            {
                "files": {"file": ("note.txt", b"hi", "text/plain")},
                "data": {"kind": "other", "title": "Нотатка"},
            },
        ),
    ),
    (
        "DELETE document",
        "editor",
        204,
        lambda w: ("DELETE", f"/api/documents/{w.document_id}", {}),
    ),
    # ---- admin: owner only --------------------------------------------------
    (
        "PATCH car",
        "owner",
        200,
        lambda w: ("PATCH", f"/api/cars/{w.car_id}", {"json": {"current_odometer": 200_500}}),
    ),
    ("DELETE car", "owner", 204, lambda w: ("DELETE", f"/api/cars/{w.car_id}", {})),
    (
        "POST interval",
        "owner",
        201,
        lambda w: (
            "POST",
            f"/api/cars/{w.car_id}/intervals",
            {"json": {"title": "Гальмівна рідина", "interval_days": 730}},
        ),
    ),
    (
        "PATCH interval",
        "owner",
        200,
        lambda w: (
            "PATCH",
            f"/api/intervals/{w.interval_id}",
            {"json": {"interval_km": 20000}},
        ),
    ),
    (
        "DELETE interval",
        "owner",
        204,
        lambda w: ("DELETE", f"/api/intervals/{w.interval_id}", {}),
    ),
    (
        "POST spec",
        "owner",
        201,
        lambda w: (
            "POST",
            f"/api/cars/{w.car_id}/specs",
            {"json": {"category": "Допуски", "name": "Фільтр", "value": "MANN"}},
        ),
    ),
    (
        "POST spec preset",
        "owner",
        201,
        lambda w: ("POST", f"/api/cars/{w.car_id}/specs/preset?key=golf7_16tdi", {}),
    ),
    (
        "PATCH spec",
        "owner",
        200,
        lambda w: ("PATCH", f"/api/specs/{w.spec_id}", {"json": {"value": "VW 504.00"}}),
    ),
    ("DELETE spec", "owner", 204, lambda w: ("DELETE", f"/api/specs/{w.spec_id}", {})),
)

ENDPOINT_IDS = [entry[0] for entry in ENDPOINTS]


def expected_status(role: str, min_role: str, ok_status: int) -> int:
    """What the matrix says: 404 for outsiders, 403 for the under-ranked."""
    if role == "stranger":
        return 404
    if ROLE_RANK[role] >= ROLE_RANK[min_role]:
        return ok_status
    return 403


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=ENDPOINT_IDS)
@pytest.mark.parametrize("role", ROLES)
def test_access_matrix(client: TestClient, world, actor, role: str, endpoint: tuple) -> None:
    _, min_role, ok_status, build = endpoint
    method, url, kwargs = build(world)

    response = client.request(method, url, headers=actor(role), **kwargs)

    assert response.status_code == expected_status(role, min_role, ok_status), response.text


@pytest.mark.parametrize("role", ROLES)
def test_missing_car_is_404_for_everyone(client: TestClient, world, actor, role: str) -> None:
    """A car id that never existed reads the same as one that is not yours."""
    assert client.get("/api/cars/999999", headers=actor(role)).status_code == 404


# The named rules from the plan, spelled out


def test_viewer_writing_is_403_not_404(client: TestClient, world, actor) -> None:
    response = client.post(
        f"/api/cars/{world.car_id}/logs",
        json={
            "type": "expense",
            "odometer": 200_200,
            "date": TODAY.isoformat(),
            "total_cost": 10,
        },
        headers=actor("viewer"),
    )
    assert response.status_code == 403


def test_editor_cannot_patch_the_car(client: TestClient, world, actor) -> None:
    response = client.patch(
        f"/api/cars/{world.car_id}",
        json={"brand": "Škoda"},
        headers=actor("editor"),
    )
    assert response.status_code == 403


def test_stranger_never_learns_the_car_exists(client: TestClient, world, actor) -> None:
    headers = actor("stranger")
    for url in (
        f"/api/cars/{world.car_id}",
        f"/api/cars/{world.car_id}/logs",
        f"/api/logs/{world.log_id}",
        f"/api/photos/{world.photo_id}",
        f"/api/obd/{world.obd_id}",
        f"/api/documents/{world.document_id}",
    ):
        assert client.get(url, headers=headers).status_code == 404, url


# Listing and your_role


def test_garage_lists_owned_and_shared_cars_without_duplicates(
    client: TestClient, world, actor, make_car, db_session_factory
) -> None:
    editor_headers = actor("editor")
    own = make_car(headers=editor_headers, brand="Mazda")

    listed = client.get("/api/cars", headers=editor_headers).json()

    assert [car["id"] for car in listed] == sorted([world.car_id, own["id"]])


def test_a_created_car_gets_its_owner_membership_row(world, db_session_factory) -> None:
    """New cars hold the same invariant migration 0008 backfills for old ones."""
    with db_session_factory() as db:
        members = (
            db.execute(select(CarMember).where(CarMember.car_id == world.car_id))
            .scalars()
            .all()
        )

    assert [(m.user_id, m.role) for m in members] == [(world.owner_id, "owner")]


def test_owner_membership_row_does_not_duplicate_the_car(
    client: TestClient, world, db_session_factory
) -> None:
    """The owner row and cars.user_id are the same access, listed once."""
    listed = client.get("/api/cars", headers=world.owner_headers).json()

    assert [car["id"] for car in listed] == [world.car_id]


@pytest.mark.parametrize("role", ("owner", "editor", "viewer"))
def test_car_out_reports_your_role(client: TestClient, world, actor, role: str) -> None:
    headers = actor(role)

    detail = client.get(f"/api/cars/{world.car_id}", headers=headers).json()
    listed = client.get("/api/cars", headers=headers).json()

    assert detail["your_role"] == role
    assert [car["your_role"] for car in listed] == [role]


def test_created_car_reports_owner_role(client: TestClient, make_car) -> None:
    assert make_car()["your_role"] == "owner"


# Helpers, directly


def test_user_role_for_car_prefers_ownership_over_a_membership_row(
    world, db_session_factory
) -> None:
    """An owner is an owner even if a row says otherwise — cars.user_id wins."""
    with db_session_factory() as db:
        owner = db.get(User, world.owner_id)
        car = db.get(Car, world.car_id)
        # demote the owner's own membership row: it must not matter
        membership = db.execute(
            select(CarMember).where(
                CarMember.car_id == car.id, CarMember.user_id == owner.id
            )
        ).scalar_one()
        membership.role = "viewer"
        db.commit()

        assert user_role_for_car(db, owner, car) == "owner"


def test_user_role_for_car_is_none_for_a_stranger(world, actor, db_session_factory) -> None:
    actor("stranger")
    with db_session_factory() as db:
        stranger = db.execute(
            select(User).where(User.email == "stranger@example.com")
        ).scalar_one()
        car = db.get(Car, world.car_id)

        assert user_role_for_car(db, stranger, car) is None


def test_list_accessible_cars_is_ordered_by_id(world, actor, db_session_factory) -> None:
    actor("viewer")
    with db_session_factory() as db:
        viewer = db.execute(
            select(User).where(User.email == "viewer@example.com")
        ).scalar_one()
        db.add(Car(user_id=viewer.id, brand="Mazda", model="6", year=2012, fuel_type="petrol"))
        db.commit()

        cars = list_accessible_cars(db, viewer)

        assert [car.id for car in cars] == sorted(car.id for car in cars)
        assert len(cars) == 2


def test_an_unknown_min_role_is_a_loud_error_not_a_free_pass(
    world, db_session_factory
) -> None:
    """A typo in a route's min_role must break, not grant everyone access."""
    with db_session_factory() as db:
        owner = db.get(User, world.owner_id)
        with pytest.raises(ValueError, match="Unknown min_role"):
            get_accessible_car(db, owner, world.car_id, min_role="admin")


def test_unknown_role_on_a_membership_row_grants_nothing(
    client: TestClient, world, actor, db_session_factory
) -> None:
    headers = actor("stranger")
    with db_session_factory() as db:
        user = db.execute(
            select(User).where(User.email == "stranger@example.com")
        ).scalar_one()
        db.add(CarMember(car_id=world.car_id, user_id=user.id, role="admin"))
        db.commit()

    assert client.get(f"/api/cars/{world.car_id}", headers=headers).status_code == 403


# Shared storage


def test_a_photo_an_editor_uploads_is_readable_by_the_owner(
    client: TestClient, world, actor
) -> None:
    """Files are keyed by the car's owner, not by whoever uploaded them —
    otherwise a shared car's photos 404 for everyone but the uploader."""
    created = client.post(
        f"/api/logs/{world.log_id}/photos",
        files={"file": ("editor.jpg", JPEG_BYTES, "image/jpeg")},
        headers=actor("editor"),
    )
    assert created.status_code == 201, created.text
    photo_id = created.json()["id"]

    for headers in (world.owner_headers, actor("viewer")):
        response = client.get(f"/api/photos/{photo_id}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.content == JPEG_BYTES
