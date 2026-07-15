"""Adversarial probes against the sharing rules — the finalizer's gate.

These are not a second copy of the access matrix (tests/test_access.py owns
that). They are the specific attacks the sharing epic invites, written from
the attacker's side:

* a viewer who tries to write;
* an editor who tries to administer, or to promote themselves;
* a stranger fishing for the existence of a car by id;
* a link replayed, a link expired, a membership revoked mid-session.

The rule under all of them is the one from the plan: «not yours» is 404 and
never 403, because 403 confirms the thing is there.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import CarInvite, CarMember, User
from app.routers.auth import register_limiter

TODAY = dt.date.today()
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-body"


@pytest.fixture()
def enroll(make_user):

    def _enroll(email: str) -> dict[str, str]:
        register_limiter.clear()
        return make_user(email)

    return _enroll


@pytest.fixture()
def shared(client: TestClient, enroll, db_session_factory: sessionmaker):
    """An owner's car with an editor, a viewer and a stranger standing by.

    The editor and viewer join the way a real one does — through an invite
    link — so the probes exercise the path that actually grants access.
    """
    owner_headers = enroll("owner@example.com")
    editor_headers = enroll("editor@example.com")
    viewer_headers = enroll("viewer@example.com")
    stranger_headers = enroll("stranger@example.com")

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

    for headers, role in ((editor_headers, "editor"), (viewer_headers, "viewer")):
        token = client.post(
            f"/api/cars/{car['id']}/invites", json={"role": role}, headers=owner_headers
        ).json()["token"]
        assert client.post(f"/api/invites/{token}/accept", headers=headers).status_code == 201

    members = client.get(f"/api/cars/{car['id']}/members", headers=owner_headers).json()
    by_role = {m["role"]: m for m in members}

    with db_session_factory() as db:
        stranger_id = db.execute(
            select(User.id).where(User.email == "stranger@example.com")
        ).scalar_one()

    return SimpleNamespace(
        owner_headers=owner_headers,
        editor_headers=editor_headers,
        viewer_headers=viewer_headers,
        stranger_headers=stranger_headers,
        stranger_id=stranger_id,
        car_id=car["id"],
        log_id=log["id"],
        interval_id=interval["id"],
        editor_member_id=by_role["editor"]["id"],
        viewer_member_id=by_role["viewer"]["id"],
        owner_member_id=by_role["owner"]["id"],
    )


# (a) A viewer reads but does not write


def test_viewer_can_read_a_log_but_cannot_write_one(client: TestClient, shared) -> None:
    """403, not 404: the viewer can plainly see the car, so hiding it would only puzzle."""
    read = client.get(f"/api/logs/{shared.log_id}", headers=shared.viewer_headers)
    assert read.status_code == 200, read.text

    write = client.post(
        f"/api/cars/{shared.car_id}/logs",
        json={
            "type": "expense",
            "odometer": 200_200,
            "date": TODAY.isoformat(),
            "total_cost": 10,
        },
        headers=shared.viewer_headers,
    )
    assert write.status_code == 403, write.text


def test_viewer_write_attempt_leaves_no_trace(client: TestClient, shared) -> None:
    """A refused write must not be a half-applied one."""
    before = client.get(f"/api/cars/{shared.car_id}/logs", headers=shared.owner_headers)
    client.post(
        f"/api/cars/{shared.car_id}/logs",
        json={
            "type": "expense",
            "odometer": 999_999,
            "date": TODAY.isoformat(),
            "total_cost": 10,
        },
        headers=shared.viewer_headers,
    )
    after = client.get(f"/api/cars/{shared.car_id}/logs", headers=shared.owner_headers)
    assert after.json()["total"] == before.json()["total"]
    # The odometer side effect must not have fired either.
    car = client.get(f"/api/cars/{shared.car_id}", headers=shared.owner_headers).json()
    assert car["current_odometer"] == 200_100


# (b) An editor writes logs but does not administer the car


def test_editor_can_patch_a_log(client: TestClient, shared) -> None:
    response = client.patch(
        f"/api/logs/{shared.log_id}",
        json={"total_cost": 30},
        headers=shared.editor_headers,
    )
    assert response.status_code == 200, response.text


def test_editor_cannot_patch_the_car(client: TestClient, shared) -> None:
    response = client.patch(
        f"/api/cars/{shared.car_id}",
        json={"current_odometer": 300_000},
        headers=shared.editor_headers,
    )
    assert response.status_code == 403, response.text


def test_editor_cannot_touch_the_cars_intervals(client: TestClient, shared) -> None:
    """Service rules are the owner's: create, edit and delete are all closed."""
    create = client.post(
        f"/api/cars/{shared.car_id}/intervals",
        json={"title": "Гальмівна рідина", "interval_days": 730},
        headers=shared.editor_headers,
    )
    patch = client.patch(
        f"/api/intervals/{shared.interval_id}",
        json={"interval_km": 20000},
        headers=shared.editor_headers,
    )
    delete = client.delete(
        f"/api/intervals/{shared.interval_id}", headers=shared.editor_headers
    )
    assert [create.status_code, patch.status_code, delete.status_code] == [403, 403, 403]


def test_editor_may_still_complete_an_interval(client: TestClient, shared) -> None:
    response = client.post(
        f"/api/intervals/{shared.interval_id}/complete",
        json={"odometer": 200_300, "date": TODAY.isoformat(), "total_cost": 50},
        headers=shared.editor_headers,
    )
    assert response.status_code == 201, response.text


# (c) A stranger gets 404 on every id route — never 403

# Every route in the app that takes an id a stranger could guess.
STRANGER_PROBES: tuple[tuple[str, str, str, dict], ...] = (
    ("GET car", "GET", "/api/cars/{car_id}", {}),
    ("PATCH car", "PATCH", "/api/cars/{car_id}", {"json": {"current_odometer": 1}}),
    ("DELETE car", "DELETE", "/api/cars/{car_id}", {}),
    ("GET logs", "GET", "/api/cars/{car_id}/logs", {}),
    (
        "POST log",
        "POST",
        "/api/cars/{car_id}/logs",
        {"json": {"type": "expense", "odometer": 1, "date": TODAY.isoformat(), "total_cost": 1}},
    ),
    ("GET log", "GET", "/api/logs/{log_id}", {}),
    ("PATCH log", "PATCH", "/api/logs/{log_id}", {"json": {"total_cost": 1}}),
    ("DELETE log", "DELETE", "/api/logs/{log_id}", {}),
    ("GET refuel-context", "GET", "/api/cars/{car_id}/refuel-context", {}),
    ("GET analytics", "GET", "/api/cars/{car_id}/analytics", {}),
    ("GET report", "GET", "/api/cars/{car_id}/report", {}),
    ("GET export.csv", "GET", "/api/cars/{car_id}/export.csv", {}),
    ("GET intervals", "GET", "/api/cars/{car_id}/intervals", {}),
    (
        "POST interval",
        "POST",
        "/api/cars/{car_id}/intervals",
        {"json": {"title": "x", "interval_km": 1}},
    ),
    ("PATCH interval", "PATCH", "/api/intervals/{interval_id}", {"json": {"interval_km": 1}}),
    ("DELETE interval", "DELETE", "/api/intervals/{interval_id}", {}),
    (
        "POST interval complete",
        "POST",
        "/api/intervals/{interval_id}/complete",
        {"json": {"odometer": 1, "date": TODAY.isoformat(), "total_cost": 1}},
    ),
    ("GET specs", "GET", "/api/cars/{car_id}/specs", {}),
    (
        "POST spec",
        "POST",
        "/api/cars/{car_id}/specs",
        {"json": {"category": "Допуски", "name": "x", "value": "y"}},
    ),
    ("POST spec preset", "POST", "/api/cars/{car_id}/specs/preset?key=golf7_16tdi", {}),
    ("GET documents", "GET", "/api/cars/{car_id}/documents", {}),
    ("GET obd list", "GET", "/api/cars/{car_id}/obd", {}),
    ("POST photo", "POST", "/api/logs/{log_id}/photos", {"files": {"file": ("x.jpg", JPEG, "image/jpeg")}}),
    # sharing surface
    ("GET members", "GET", "/api/cars/{car_id}/members", {}),
    ("POST invite", "POST", "/api/cars/{car_id}/invites", {"json": {"role": "viewer"}}),
    ("PATCH member", "PATCH", "/api/members/{editor_member_id}", {"json": {"role": "viewer"}}),
    ("DELETE member", "DELETE", "/api/members/{editor_member_id}", {}),
)

STRANGER_IDS = [probe[0] for probe in STRANGER_PROBES]


@pytest.mark.parametrize("probe", STRANGER_PROBES, ids=STRANGER_IDS)
def test_stranger_gets_404_never_403(client: TestClient, shared, probe: tuple) -> None:
    """A 403 here would confirm the resource exists. Only 404 may come back."""
    _, method, template, kwargs = probe
    url = template.format(
        car_id=shared.car_id,
        log_id=shared.log_id,
        interval_id=shared.interval_id,
        editor_member_id=shared.editor_member_id,
    )
    response = client.request(method, url, headers=shared.stranger_headers, **kwargs)
    assert response.status_code == 404, (
        f"{method} {url} answered {response.status_code} to a stranger; "
        f"only 404 may be returned. Body: {response.text}"
    )


@pytest.mark.parametrize("probe", STRANGER_PROBES, ids=STRANGER_IDS)
def test_stranger_sees_the_same_answer_for_a_real_and_a_fake_id(
    client: TestClient, shared, probe: tuple
) -> None:
    """The real id and an id that never existed must be indistinguishable."""
    _, method, template, kwargs = probe
    real = template.format(
        car_id=shared.car_id,
        log_id=shared.log_id,
        interval_id=shared.interval_id,
        editor_member_id=shared.editor_member_id,
    )
    fake = template.format(
        car_id=987_654, log_id=987_654, interval_id=987_654, editor_member_id=987_654
    )
    real_response = client.request(method, real, headers=shared.stranger_headers, **kwargs)
    fake_response = client.request(method, fake, headers=shared.stranger_headers, **kwargs)
    assert real_response.status_code == fake_response.status_code == 404
    assert real_response.json() == fake_response.json(), (
        "the response body differs between a real and an imaginary id, which "
        "tells an outsider the real one is real"
    )


# (d) + (e) Invite replay and expiry


def test_accepting_an_invite_twice_does_not_duplicate_membership(
    client: TestClient, shared, enroll, db_session_factory: sessionmaker
) -> None:
    friend_headers = enroll("friend@example.com")
    token = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "editor"},
        headers=shared.owner_headers,
    ).json()["token"]

    first = client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert first.status_code == 201, first.text

    # The token is spent, so the replay is refused outright.
    second = client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert second.status_code == 404, second.text

    with db_session_factory() as db:
        friend_id = db.execute(
            select(User.id).where(User.email == "friend@example.com")
        ).scalar_one()
        count = db.execute(
            select(func.count())
            .select_from(CarMember)
            .where(CarMember.car_id == shared.car_id, CarMember.user_id == friend_id)
        ).scalar_one()
    assert count == 1


def test_a_second_live_link_does_not_duplicate_an_existing_member(
    client: TestClient, shared, db_session_factory: sessionmaker
) -> None:
    token = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "viewer"},
        headers=shared.owner_headers,
    ).json()["token"]

    response = client.post(f"/api/invites/{token}/accept", headers=shared.editor_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_member"] is True
    # A link must never *lower* a standing role.
    assert body["role"] == "editor"

    with db_session_factory() as db:
        count = db.execute(
            select(func.count())
            .select_from(CarMember)
            .where(CarMember.car_id == shared.car_id)
        ).scalar_one()
    assert count == 3  # owner + editor + viewer, unchanged


def test_a_used_token_is_404(client: TestClient, shared, enroll) -> None:
    friend_headers = enroll("friend@example.com")
    other_headers = enroll("other@example.com")
    token = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "editor"},
        headers=shared.owner_headers,
    ).json()["token"]
    assert client.post(f"/api/invites/{token}/accept", headers=friend_headers).status_code == 201

    # Spent by the first taker — nobody else gets in with it.
    assert client.post(f"/api/invites/{token}/accept", headers=other_headers).status_code == 404
    assert client.get(f"/api/invites/{token}", headers=other_headers).status_code == 404


def test_an_expired_token_is_404(
    client: TestClient, shared, enroll, db_session_factory: sessionmaker
) -> None:
    friend_headers = enroll("friend@example.com")
    token = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "editor"},
        headers=shared.owner_headers,
    ).json()["token"]

    with db_session_factory() as db:
        for invite in db.execute(select(CarInvite)).scalars().all():
            invite.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        db.commit()

    assert client.get(f"/api/invites/{token}", headers=friend_headers).status_code == 404
    assert client.post(f"/api/invites/{token}/accept", headers=friend_headers).status_code == 404


def test_an_expired_token_grants_nothing(
    client: TestClient, shared, enroll, db_session_factory: sessionmaker
) -> None:
    friend_headers = enroll("friend@example.com")
    token = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "editor"},
        headers=shared.owner_headers,
    ).json()["token"]
    with db_session_factory() as db:
        for invite in db.execute(select(CarInvite)).scalars().all():
            invite.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        db.commit()
    client.post(f"/api/invites/{token}/accept", headers=friend_headers)

    assert client.get(f"/api/cars/{shared.car_id}", headers=friend_headers).status_code == 404


# (f) Revocation is immediate


def test_removing_a_member_revokes_access_immediately(client: TestClient, shared) -> None:
    """The very next request from a live session must already be 404."""
    assert client.get(f"/api/cars/{shared.car_id}", headers=shared.editor_headers).status_code == 200

    removed = client.delete(
        f"/api/members/{shared.editor_member_id}", headers=shared.owner_headers
    )
    assert removed.status_code == 204, removed.text

    # Same token, no re-login: access is decided per request, not per session.
    assert client.get(f"/api/cars/{shared.car_id}", headers=shared.editor_headers).status_code == 404
    assert client.get(f"/api/cars/{shared.car_id}/logs", headers=shared.editor_headers).status_code == 404
    assert (
        client.get(f"/api/logs/{shared.log_id}", headers=shared.editor_headers).status_code == 404
    )
    # And the car is gone from their garage.
    garage = client.get("/api/cars", headers=shared.editor_headers).json()
    assert garage == []


def test_leaving_revokes_your_own_access_immediately(client: TestClient, shared) -> None:
    left = client.delete(
        f"/api/members/{shared.viewer_member_id}", headers=shared.viewer_headers
    )
    assert left.status_code == 204, left.text
    assert client.get(f"/api/cars/{shared.car_id}", headers=shared.viewer_headers).status_code == 404


def test_a_removed_member_cannot_use_an_old_invite_preview(
    client: TestClient, shared
) -> None:
    client.delete(f"/api/members/{shared.editor_member_id}", headers=shared.owner_headers)
    # The link that let them in was spent on the way in.
    assert client.get(f"/api/cars/{shared.car_id}", headers=shared.editor_headers).status_code == 404


# (g) No self-escalation


def test_editor_cannot_promote_themselves(client: TestClient, shared) -> None:
    for role in ("owner", "editor", "viewer"):
        response = client.patch(
            f"/api/members/{shared.editor_member_id}",
            json={"role": role},
            headers=shared.editor_headers,
        )
        assert response.status_code == 403, (
            f"an editor patching their own row to {role!r} got "
            f"{response.status_code}: {response.text}"
        )


def test_editor_cannot_promote_the_viewer(client: TestClient, shared) -> None:
    response = client.patch(
        f"/api/members/{shared.viewer_member_id}",
        json={"role": "editor"},
        headers=shared.editor_headers,
    )
    assert response.status_code == 403, response.text


def test_viewer_cannot_promote_themselves(client: TestClient, shared) -> None:
    response = client.patch(
        f"/api/members/{shared.viewer_member_id}",
        json={"role": "editor"},
        headers=shared.viewer_headers,
    )
    assert response.status_code == 403, response.text


def test_self_promotion_attempt_does_not_change_the_stored_role(
    client: TestClient, shared, db_session_factory: sessionmaker
) -> None:
    client.patch(
        f"/api/members/{shared.editor_member_id}",
        json={"role": "owner"},
        headers=shared.editor_headers,
    )
    with db_session_factory() as db:
        role = db.execute(
            select(CarMember.role).where(CarMember.id == shared.editor_member_id)
        ).scalar_one()
    assert role == "editor"
    # And the car still answers to exactly one owner.
    assert client.patch(
        f"/api/cars/{shared.car_id}",
        json={"current_odometer": 300_000},
        headers=shared.editor_headers,
    ).status_code == 403


def test_nobody_can_be_granted_owner_through_membership(client: TestClient, shared) -> None:
    """Even the owner cannot mint a second owner: cars.user_id is the only source."""
    response = client.patch(
        f"/api/members/{shared.editor_member_id}",
        json={"role": "owner"},
        headers=shared.owner_headers,
    )
    assert response.status_code == 400, response.text


def test_editor_cannot_remove_the_viewer(client: TestClient, shared) -> None:
    response = client.delete(
        f"/api/members/{shared.viewer_member_id}", headers=shared.editor_headers
    )
    assert response.status_code == 403, response.text


def test_editor_cannot_mint_an_invite(client: TestClient, shared) -> None:
    """Sharing further is the owner's call — an editor cannot widen the circle."""
    response = client.post(
        f"/api/cars/{shared.car_id}/invites",
        json={"role": "editor"},
        headers=shared.editor_headers,
    )
    assert response.status_code == 403, response.text
