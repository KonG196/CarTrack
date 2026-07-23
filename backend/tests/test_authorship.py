"""Who wrote each entry: author on create, never on edit, null for legacy.

The author is bookkeeping, not history: a shared car needs to show who filled
the tank, but nothing in the app may depend on an author being there. Every
entry written before sharing existed has none, and those rows must keep
serializing, reporting and totalling exactly as they did.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_access_token
from app.bot import service
from app.models import Car, CarMember, LogEntry, RefuelDetails, ServiceInterval, User
from app.services.intervals_complete import complete_interval

FRIEND_EMAIL = "friend@example.com"


def _log_payload(odometer: int = 12000, **overrides) -> dict:
    payload = {
        "type": "expense",
        "odometer": odometer,
        "date": dt.date.today().isoformat(),
        "total_cost": 250,
        "expense": {"category": "Мийка"},
    }
    payload.update(overrides)
    return payload


def _share_with(
    client: TestClient, owner: dict, car_id: int, member: dict, role: str = "editor"
) -> None:
    token = client.post(
        f"/api/cars/{car_id}/invites", json={"role": role}, headers=owner
    ).json()["token"]
    assert client.post(f"/api/invites/{token}/accept", headers=member).status_code == 201


# Author on create (API)


def test_created_log_carries_its_author(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=auth_headers
    )
    assert response.status_code == 201, response.text
    author = response.json()["author"]
    assert author is not None
    assert author["label"] == "user"  # email handle, no display name set
    assert isinstance(author["id"], int)


def test_author_is_the_writer_not_the_owner(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)

    created = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    )
    assert created.status_code == 201
    assert created.json()["author"]["label"] == "friend"

    # And the owner reading the same car sees the friend's name on it.
    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers).json()
    assert listed["items"][0]["author"]["label"] == "friend"


def test_author_label_prefers_display_name(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    client.patch("/api/auth/me", json={"display_name": "Тато"}, headers=auth_headers)
    response = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=auth_headers
    )
    assert response.json()["author"]["label"] == "Тато"


def test_author_appears_on_list_and_detail(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    log_id = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=auth_headers
    ).json()["id"]

    detail = client.get(f"/api/logs/{log_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["author"]["label"] == "user"

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers).json()
    assert listed["items"][0]["author"]["label"] == "user"


def test_interval_completion_records_its_author(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)
    interval_id = client.post(
        f"/api/cars/{car['id']}/intervals",
        json={"title": "Заміна оливи", "interval_km": 10000},
        headers=auth_headers,
    ).json()["id"]

    response = client.post(
        f"/api/intervals/{interval_id}/complete",
        json={"odometer": 15000, "date": dt.date.today().isoformat()},
        headers=friend,
    )
    assert response.status_code == 201, response.text
    assert response.json()["log"]["author"]["label"] == "friend"


# PATCH never reassigns the author


def test_patch_does_not_change_the_author(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)
    log_id = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    ).json()["id"]

    patched = client.patch(
        f"/api/logs/{log_id}", json={"total_cost": 999}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["total_cost"] == 999.0
    assert patched.json()["author"]["label"] == "friend"


def test_patch_cannot_smuggle_an_author(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    """author/author_id in the body are not fields — they must be ignored."""
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)
    friend_id = client.get("/api/auth/me", headers=friend).json()["id"]
    log_id = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=auth_headers
    ).json()["id"]

    patched = client.patch(
        f"/api/logs/{log_id}",
        json={"notes": "hi", "author_id": friend_id, "author": {"id": friend_id}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["author"]["label"] == "user"


def test_create_cannot_smuggle_an_author(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)
    friend_id = client.get("/api/auth/me", headers=friend).json()["id"]

    created = client.post(
        f"/api/cars/{car['id']}/logs",
        json=_log_payload(author_id=friend_id),
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["author"]["label"] == "user"


# Legacy rows (author_id NULL) — nothing may depend on an author


def _legacy_log(db: Session, car_id: int, odometer: int = 11000) -> LogEntry:
    log = LogEntry(
        car_id=car_id,
        author_id=None,
        type="refuel",
        odometer=odometer,
        date=dt.date.today() - dt.timedelta(days=5),
        total_cost=1200,
    )
    db.add(log)
    db.flush()
    db.add(
        RefuelDetails(
            log_entry_id=log.id,
            liters=40,
            price_per_liter=30,
            is_full_tank=True,
        )
    )
    db.commit()
    return log


def test_legacy_log_serializes_with_null_author(
    client: TestClient, auth_headers: dict, make_car: Callable, db_session_factory
) -> None:
    car = make_car()
    with db_session_factory() as db:
        log = _legacy_log(db, car["id"])
        log_id = log.id

    detail = client.get(f"/api/logs/{log_id}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["author"] is None

    listed = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["author"] is None


def test_legacy_log_does_not_break_report_analytics_or_export(
    client: TestClient, auth_headers: dict, make_car: Callable, db_session_factory
) -> None:
    car = make_car()
    with db_session_factory() as db:
        _legacy_log(db, car["id"])

    assert client.get(f"/api/cars/{car['id']}/report", headers=auth_headers).status_code == 200
    assert client.get(f"/api/cars/{car['id']}/analytics", headers=auth_headers).status_code == 200
    assert client.get(f"/api/cars/{car['id']}/export.csv", headers=auth_headers).status_code == 200
    assert client.get("/api/export", headers=auth_headers).status_code == 200


def test_mixed_authored_and_legacy_logs_list_together(
    client: TestClient, auth_headers: dict, make_car: Callable, db_session_factory
) -> None:
    car = make_car()
    with db_session_factory() as db:
        _legacy_log(db, car["id"])
    client.post(f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=auth_headers)

    items = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers).json()["items"]
    authors = [item["author"] for item in items]
    assert None in authors
    assert any(a is not None and a["label"] == "user" for a in authors)


# N+1 guard


def _add_editors(db_session_factory, car_id: int, emails: list[str]) -> list[dict]:
    """Seed extra editors straight into the database, with usable tokens.

    Registering them over HTTP would be the honest path, but /register is
    rate-limited to 3 per hour per IP and the whole suite shares one client
    IP. What is under test here is the eager-load, not the sign-up flow.
    """
    headers: list[dict] = []
    with db_session_factory() as db:
        for email in emails:
            user = User(email=email, hashed_password="x")
            db.add(user)
            db.flush()
            db.add(CarMember(car_id=car_id, user_id=user.id, role="editor"))
            headers.append({"Authorization": f"Bearer {create_access_token(user.id)}"})
        db.commit()
    return headers


def test_log_list_query_count_does_not_grow_with_authors(
    client: TestClient,
    auth_headers: dict,
    make_car: Callable,
    db_session_factory,
    db_engine,
) -> None:
    """The author must be eager-loaded: one query for all of them, not one each.

    The two runs differ in how many DISTINCT authors they hold, which is what
    a lazy load would actually charge for — per-row loading of a many-to-one
    is served from the identity map after the first hit, so counting rows
    alone would let an N+1 slip through.
    """
    counts: list[int] = []
    for index, n_logs in enumerate((2, 12)):
        car = make_car()
        writers = [auth_headers] + _add_editors(
            db_session_factory,
            car["id"],
            [f"writer{index}-{w}@example.com" for w in range(3)],
        )
        for i in range(n_logs):
            client.post(
                f"/api/cars/{car['id']}/logs",
                json=_log_payload(odometer=12000 + i * 100),
                headers=writers[i % len(writers)],
            )

        statements: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db_engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
        finally:
            event.remove(db_engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        assert all(item["author"] is not None for item in response.json()["items"])
        counts.append(len(statements))

    assert counts[0] == counts[1], f"query count grew with log count: {counts}"


# The bot writes its author too


def _bot_user_with_car(db: Session, email: str = "bot@example.com") -> tuple[User, Car]:
    user = User(email=email, hashed_password="x", telegram_chat_id="42")
    db.add(user)
    db.flush()
    car = Car(
        user_id=user.id,
        brand="Skoda",
        model="Octavia",
        year=2018,
        fuel_type="diesel",
        current_odometer=50000,
    )
    db.add(car)
    db.commit()
    return user, car


def test_bot_quick_expense_records_the_author(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, car = _bot_user_with_car(db)
        log = service.create_quick_expense(db, car.id, "мийка", 300, author_id=user.id)
        assert log is not None
        assert log.author_id == user.id


def test_bot_refuel_records_the_author(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        user, car = _bot_user_with_car(db)
        log = service.create_refuel(
            db,
            car.id,
            liters=40,
            price_per_liter=55,
            total_cost=2200,
            author_id=user.id,
        )
        assert log is not None
        assert log.author_id == user.id


def test_bot_writes_without_an_author_stay_valid(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        _user, car = _bot_user_with_car(db)
        log = service.create_quick_expense(db, car.id, "мийка", 300)
        assert log is not None
        assert log.author_id is None


def test_interval_completion_author_is_optional(
    db_session_factory: sessionmaker,
) -> None:
    with db_session_factory() as db:
        user, car = _bot_user_with_car(db)
        interval = ServiceInterval(car_id=car.id, title="Оливка", interval_km=10000)
        db.add(interval)
        db.commit()

        completion = complete_interval(
            db, interval, odometer=51000, date=dt.date.today(), author_id=user.id
        )
        assert completion.log.author_id == user.id


# Profile: display_name


def test_me_reports_display_name(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_patch_me_sets_display_name(client: TestClient, auth_headers: dict) -> None:
    response = client.patch(
        "/api/auth/me", json={"display_name": "Тато"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Тато"
    assert client.get("/api/auth/me", headers=auth_headers).json()["display_name"] == "Тато"


def test_patch_me_trims_display_name(client: TestClient, auth_headers: dict) -> None:
    response = client.patch(
        "/api/auth/me", json={"display_name": "  Тато  "}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Тато"


def test_patch_me_rejects_blank_display_name(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/api/auth/me", json={"display_name": "   "}, headers=auth_headers
    )
    assert response.status_code == 422


def test_patch_me_rejects_too_long_display_name(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/api/auth/me", json={"display_name": "я" * 81}, headers=auth_headers
    )
    assert response.status_code == 422


def test_patch_me_clears_display_name_with_null(
    client: TestClient, auth_headers: dict
) -> None:
    client.patch("/api/auth/me", json={"display_name": "Тато"}, headers=auth_headers)
    response = client.patch(
        "/api/auth/me", json={"display_name": None}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_patch_me_requires_auth(client: TestClient) -> None:
    assert client.patch("/api/auth/me", json={"display_name": "Тато"}).status_code == 401


def test_patch_me_only_touches_the_caller(
    client: TestClient, auth_headers: dict, make_user: Callable
) -> None:
    friend = make_user(email=FRIEND_EMAIL)
    client.patch("/api/auth/me", json={"display_name": "Тато"}, headers=auth_headers)
    assert client.get("/api/auth/me", headers=friend).json()["display_name"] is None


def test_deleting_an_author_orphans_their_shared_car_logs(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    """A member who deletes their account must not leave a dangling author_id: on
    SQLite the freed user id is reused, so a future signup would inherit it and be
    shown as the author of entries they never wrote."""
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _share_with(client, auth_headers, car["id"], friend)

    created = client.post(f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend)
    assert created.status_code == 201
    log_id = created.json()["id"]

    # Friend deletes their account.
    deleted = client.request(
        "DELETE", "/api/auth/me", json={"password": "secret123"}, headers=friend
    )
    assert deleted.status_code in (200, 204)

    # The owner still sees the entry, but it now has no author (not a reused one).
    detail = client.get(f"/api/logs/{log_id}", headers=auth_headers).json()
    assert detail["author"] is None
