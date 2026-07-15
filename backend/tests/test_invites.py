"""Invite lifecycle: create, preview, accept, members, roles, leaving.

The invite link is the only way a car is shared, so these tests care about
two things above all: that a token grants exactly the access it says and
nothing more, and that it stops working the moment it is used or expires.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import CarInvite, CarMember

OWNER_EMAIL = "user@example.com"  # conftest's default user, who owns make_car
FRIEND_EMAIL = "friend@example.com"
STRANGER_EMAIL = "stranger@example.com"


def _invite(
    client: TestClient, headers: dict, car_id: int, role: str = "editor"
) -> dict:
    response = client.post(
        f"/api/cars/{car_id}/invites", json={"role": role}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _accept(client: TestClient, headers: dict, token: str):
    return client.post(f"/api/invites/{token}/accept", headers=headers)


def _expire_invites(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        for invite in db.execute(select(CarInvite)).scalars().all():
            invite.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        db.commit()


# Creating an invite


def test_owner_creates_invite_and_gets_token_once(
    client: TestClient, auth_headers: dict, make_car: Callable, db_session_factory
) -> None:
    car = make_car()
    body = _invite(client, auth_headers, car["id"], role="editor")

    assert body["token"]
    assert body["invite_path"] == f"/join/{body['token']}"
    assert body["expires_at"]

    # The token exists in exactly one place after the response: the caller's
    # hands. Nothing readable is left behind in the row.
    with db_session_factory() as db:
        invite = db.execute(select(CarInvite)).scalar_one()
        assert invite.token_hash != body["token"]
        assert invite.token_hash.startswith("$2")  # bcrypt
        assert body["token"] not in invite.token_hash
        assert invite.role == "editor"
        assert invite.used_by is None
        assert invite.used_at is None


def test_invite_expires_in_seven_days(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    body = _invite(client, auth_headers, car["id"])
    expires_at = dt.datetime.fromisoformat(body["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    delta = expires_at - dt.datetime.now(dt.timezone.utc)
    assert dt.timedelta(days=6, hours=23) < delta <= dt.timedelta(days=7)


def test_two_invites_have_different_tokens(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    first = _invite(client, auth_headers, car["id"])
    second = _invite(client, auth_headers, car["id"])
    assert first["token"] != second["token"]


def test_viewer_cannot_create_invite(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    token = _invite(client, auth_headers, car["id"], role="viewer")["token"]
    assert _accept(client, friend, token).status_code == 201

    response = client.post(
        f"/api/cars/{car['id']}/invites", json={"role": "viewer"}, headers=friend
    )
    assert response.status_code == 403


def test_editor_cannot_create_invite(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    assert _accept(client, friend, token).status_code == 201

    response = client.post(
        f"/api/cars/{car['id']}/invites", json={"role": "editor"}, headers=friend
    )
    assert response.status_code == 403


def test_stranger_cannot_create_invite_for_someone_elses_car(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    stranger = make_user(email=STRANGER_EMAIL)
    response = client.post(
        f"/api/cars/{car['id']}/invites", json={"role": "editor"}, headers=stranger
    )
    # Not 403: a car that is not theirs must look like a car that is not there.
    assert response.status_code == 404


def test_invite_cannot_grant_owner(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/invites", json={"role": "owner"}, headers=auth_headers
    )
    assert response.status_code == 400


def test_invite_requires_auth(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    response = client.post(f"/api/cars/{car['id']}/invites", json={"role": "editor"})
    assert response.status_code == 401


# Previewing an invite


def test_preview_shows_car_role_and_inviter(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car(brand="Volkswagen", model="Golf", year=2016)
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)

    response = client.get(f"/api/invites/{token}", headers=friend)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["car"] == {"brand": "Volkswagen", "model": "Golf", "year": 2016}
    assert body["role"] == "editor"
    # No display name set, so the inviter is signed by their email handle.
    assert body["inviter_label"] == OWNER_EMAIL.split("@")[0]


def test_preview_requires_auth(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    assert client.get(f"/api/invites/{token}").status_code == 401


def test_preview_unknown_token_404(client: TestClient, auth_headers: dict) -> None:
    assert client.get("/api/invites/nope-not-a-token", headers=auth_headers).status_code == 404


def test_preview_expired_token_404(
    client: TestClient,
    auth_headers: dict,
    make_car: Callable,
    make_user: Callable,
    db_session_factory,
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _expire_invites(db_session_factory)
    assert client.get(f"/api/invites/{token}", headers=friend).status_code == 404


def test_preview_used_token_404(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)
    assert _accept(client, friend, token).status_code == 201
    assert client.get(f"/api/invites/{token}", headers=friend).status_code == 404


# Accepting an invite


def test_accept_grants_access_at_the_invited_role(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)

    response = _accept(client, friend, token)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["car_id"] == car["id"]
    assert body["role"] == "editor"
    assert body["already_member"] is False

    # The car is now in the friend's garage, reported at the invited role.
    garage = client.get("/api/cars", headers=friend)
    assert garage.status_code == 200
    assert [item["id"] for item in garage.json()] == [car["id"]]
    assert garage.json()[0]["your_role"] == "editor"


def test_accept_marks_invite_used(
    client: TestClient,
    auth_headers: dict,
    make_car: Callable,
    make_user: Callable,
    db_session_factory,
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)
    assert _accept(client, friend, token).status_code == 201

    with db_session_factory() as db:
        invite = db.execute(select(CarInvite)).scalar_one()
        assert invite.used_at is not None
        assert invite.used_by is not None


def test_accept_is_single_use(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)
    stranger = make_user(email=STRANGER_EMAIL)

    assert _accept(client, friend, token).status_code == 201
    # Same token, second person: the link is spent.
    assert _accept(client, stranger, token).status_code == 404
    assert client.get("/api/cars", headers=stranger).json() == []


def test_accept_twice_by_same_user_404(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)

    assert _accept(client, friend, token).status_code == 201
    assert _accept(client, friend, token).status_code == 404


def test_accept_by_existing_member_is_idempotent(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    first = _invite(client, auth_headers, car["id"], role="editor")["token"]
    assert _accept(client, friend, first).status_code == 201

    second = _invite(client, auth_headers, car["id"], role="viewer")["token"]
    response = _accept(client, friend, second)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_member"] is True
    # The standing role wins: an invite never quietly demotes a member.
    assert body["role"] == "editor"
    assert client.get("/api/cars", headers=friend).json()[0]["your_role"] == "editor"


def test_owner_cannot_accept_invite_to_own_car(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    response = _accept(client, auth_headers, token)
    assert response.status_code == 400


def test_accept_expired_token_404(
    client: TestClient,
    auth_headers: dict,
    make_car: Callable,
    make_user: Callable,
    db_session_factory,
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _expire_invites(db_session_factory)

    assert _accept(client, friend, token).status_code == 404
    assert client.get("/api/cars", headers=friend).json() == []


def test_accept_unknown_token_404(client: TestClient, auth_headers: dict) -> None:
    assert _accept(client, auth_headers, "not-a-real-token").status_code == 404


def test_accept_requires_auth(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    assert client.post(f"/api/invites/{token}/accept").status_code == 401


def test_invite_is_link_based_not_addressed(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"])["token"]
    stranger = make_user(email=STRANGER_EMAIL)
    assert _accept(client, stranger, token).status_code == 201


# What each role may actually do once inside


def _log_payload(odometer: int = 12000) -> dict:
    return {
        "type": "expense",
        "odometer": odometer,
        "date": dt.date.today().isoformat(),
        "total_cost": 250,
        "expense": {"category": "Мийка"},
    }


def test_accepted_editor_can_write_logs(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)

    response = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    )
    assert response.status_code == 201, response.text


def test_accepted_viewer_can_read_but_not_write(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="viewer")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)

    assert client.get(f"/api/cars/{car['id']}/logs", headers=friend).status_code == 200
    write = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    )
    # 403, not 404: they can see the car, so hiding the reason would only puzzle.
    assert write.status_code == 403


# Members list


def test_members_list_shows_owner_and_invited(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)

    response = client.get(f"/api/cars/{car['id']}/members", headers=auth_headers)
    assert response.status_code == 200, response.text
    members = response.json()
    assert [m["role"] for m in members] == ["owner", "editor"]
    assert [m["label"] for m in members] == ["user", "friend"]
    assert [m["is_you"] for m in members] == [True, False]
    assert all(isinstance(m["id"], int) for m in members)
    assert all(m["created_at"] for m in members)


def test_members_list_is_you_is_per_caller(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)

    members = client.get(f"/api/cars/{car['id']}/members", headers=friend).json()
    assert [m["is_you"] for m in members] == [False, True]


def test_members_list_uses_display_name_when_set(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    client.patch("/api/auth/me", json={"display_name": "Тато"}, headers=auth_headers)
    members = client.get(f"/api/cars/{car['id']}/members", headers=auth_headers).json()
    assert members[0]["label"] == "Тато"


def test_viewer_can_list_members(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="viewer")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)
    assert client.get(f"/api/cars/{car['id']}/members", headers=friend).status_code == 200


def test_stranger_cannot_list_members(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    stranger = make_user(email=STRANGER_EMAIL)
    response = client.get(f"/api/cars/{car['id']}/members", headers=stranger)
    assert response.status_code == 404


# Removing members / leaving


def _member_id(client: TestClient, headers: dict, car_id: int, email: str) -> int:
    members = client.get(f"/api/cars/{car_id}/members", headers=headers).json()
    label = email.split("@")[0]
    return next(m["id"] for m in members if m["label"] == label)


def test_owner_removes_member_and_access_goes_away(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    assert client.delete(f"/api/members/{member_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/cars/{car['id']}", headers=friend).status_code == 404
    assert client.get("/api/cars", headers=friend).json() == []


def test_member_can_leave_the_car(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    token = _invite(client, auth_headers, car["id"], role="editor")["token"]
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, token)
    member_id = _member_id(client, friend, car["id"], FRIEND_EMAIL)

    assert client.delete(f"/api/members/{member_id}", headers=friend).status_code == 204
    assert client.get(f"/api/cars/{car['id']}", headers=friend).status_code == 404


def test_owner_cannot_be_removed(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    member_id = _member_id(client, auth_headers, car["id"], OWNER_EMAIL)
    response = client.delete(f"/api/members/{member_id}", headers=auth_headers)
    assert response.status_code == 400


def test_member_cannot_remove_another_member(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    stranger = make_user(email=STRANGER_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    _accept(client, stranger, _invite(client, auth_headers, car["id"], "editor")["token"])

    victim = _member_id(client, auth_headers, car["id"], STRANGER_EMAIL)
    response = client.delete(f"/api/members/{victim}", headers=friend)
    assert response.status_code == 403
    assert client.get(f"/api/cars/{car['id']}", headers=stranger).status_code == 200


def test_stranger_cannot_remove_member(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    stranger = make_user(email=STRANGER_EMAIL)
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    response = client.delete(f"/api/members/{member_id}", headers=stranger)
    assert response.status_code == 404


def test_delete_unknown_member_404(client: TestClient, auth_headers: dict) -> None:
    assert client.delete("/api/members/9999", headers=auth_headers).status_code == 404


def test_leaving_keeps_the_history_you_wrote(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    """A member walking out must not take the car's service history with them."""
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    created = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    )
    assert created.status_code == 201
    member_id = _member_id(client, friend, car["id"], FRIEND_EMAIL)
    client.delete(f"/api/members/{member_id}", headers=friend)

    logs = client.get(f"/api/cars/{car['id']}/logs", headers=auth_headers)
    assert logs.status_code == 200
    assert logs.json()["total"] == 1


# Changing a role


def test_owner_changes_member_role(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    response = client.patch(
        f"/api/members/{member_id}", json={"role": "viewer"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "viewer"
    # The demotion is real, not just reported.
    write = client.post(
        f"/api/cars/{car['id']}/logs", json=_log_payload(), headers=friend
    )
    assert write.status_code == 403


def test_role_cannot_be_set_to_owner(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    response = client.patch(
        f"/api/members/{member_id}", json={"role": "owner"}, headers=auth_headers
    )
    assert response.status_code == 400
    assert client.get(f"/api/cars/{car['id']}", headers=friend).json()["your_role"] == "editor"


def test_unknown_role_rejected(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    response = client.patch(
        f"/api/members/{member_id}", json={"role": "admin"}, headers=auth_headers
    )
    assert response.status_code == 400


def test_owner_role_row_cannot_be_changed(
    client: TestClient, auth_headers: dict, make_car: Callable
) -> None:
    car = make_car()
    member_id = _member_id(client, auth_headers, car["id"], OWNER_EMAIL)
    response = client.patch(
        f"/api/members/{member_id}", json={"role": "viewer"}, headers=auth_headers
    )
    assert response.status_code == 400
    assert client.get(f"/api/cars/{car['id']}", headers=auth_headers).json()["your_role"] == "owner"


def test_editor_cannot_change_roles(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    stranger = make_user(email=STRANGER_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    _accept(client, stranger, _invite(client, auth_headers, car["id"], "viewer")["token"])
    victim = _member_id(client, auth_headers, car["id"], STRANGER_EMAIL)

    response = client.patch(
        f"/api/members/{victim}", json={"role": "editor"}, headers=friend
    )
    assert response.status_code == 403


def test_stranger_patching_member_gets_404(
    client: TestClient, auth_headers: dict, make_car: Callable, make_user: Callable
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    stranger = make_user(email=STRANGER_EMAIL)
    member_id = _member_id(client, auth_headers, car["id"], FRIEND_EMAIL)

    response = client.patch(
        f"/api/members/{member_id}", json={"role": "viewer"}, headers=stranger
    )
    assert response.status_code == 404


# Cascades


def test_deleting_the_car_deletes_its_invites_and_members(
    client: TestClient,
    auth_headers: dict,
    make_car: Callable,
    make_user: Callable,
    db_session_factory,
) -> None:
    car = make_car()
    friend = make_user(email=FRIEND_EMAIL)
    _accept(client, friend, _invite(client, auth_headers, car["id"], "editor")["token"])
    _invite(client, auth_headers, car["id"], "viewer")  # a live one, too

    assert client.delete(f"/api/cars/{car['id']}", headers=auth_headers).status_code == 204
    with db_session_factory() as db:
        assert db.execute(select(CarInvite)).scalars().all() == []
        assert db.execute(select(CarMember)).scalars().all() == []
