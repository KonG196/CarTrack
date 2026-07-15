"""Seasonal tire set tests: CRUD, the install swap, km_on_set, and roles.

The role cases are here rather than in the shared access matrix: tire sets are
car configuration, so every write is owner-only and the read is viewer+, and
this file proves that for each of its own routes.
"""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Car, CarMember, TireSet, User

TODAY = dt.date.today()


def _create_tires(client: TestClient, headers: dict, car_id: int, **overrides) -> dict:
    payload = {"name": "Зима Nokian", "season": "winter"}
    payload.update(overrides)
    response = client.post(f"/api/cars/{car_id}/tires", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _member(db_session_factory, make_user, car_id: int, role: str) -> dict[str, str]:
    email = f"{role}@example.com"
    headers = make_user(email)
    with db_session_factory() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        db.add(CarMember(car_id=car_id, user_id=user.id, role=role))
        db.commit()
    return headers


def _set_odometer(db_session_factory, car_id: int, odometer: int) -> None:
    with db_session_factory() as db:
        car = db.execute(select(Car).where(Car.id == car_id)).scalar_one()
        car.current_odometer = odometer
        db.commit()


# CRUD


def test_create_tire_set_returns_the_stored_row(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    tires = _create_tires(
        client,
        auth_headers,
        car["id"],
        size="205/55 R16",
        dot_year=2021,
        purchased_at=TODAY.isoformat(),
    )
    assert tires["car_id"] == car["id"]
    assert tires["name"] == "Зима Nokian"
    assert tires["season"] == "winter"
    assert tires["size"] == "205/55 R16"
    assert tires["dot_year"] == 2021
    assert tires["purchased_at"] == TODAY.isoformat()
    # A new set is on the shelf, not on the car: only /install mounts it.
    assert tires["is_installed"] is False
    assert tires["odometer_at_install"] is None
    assert tires["km_on_set"] is None


def test_create_tire_set_keeps_the_optional_fields_null(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    tires = _create_tires(client, auth_headers, car["id"], name="Літо", season="summer")
    assert tires["size"] is None
    assert tires["dot_year"] is None
    assert tires["purchased_at"] is None


def test_list_tires_is_empty_for_a_new_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_tires_puts_the_installed_set_first(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    summer = _create_tires(client, auth_headers, car["id"], name="Літо", season="summer")
    winter = _create_tires(client, auth_headers, car["id"], name="Зима", season="winter")
    client.post(f"/api/tires/{winter['id']}/install", headers=auth_headers)

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert [t["id"] for t in listed] == [winter["id"], summer["id"]]


def test_list_tires_only_shows_that_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    other_car = make_car(brand="Skoda")
    _create_tires(client, auth_headers, car["id"], name="Зима")
    _create_tires(client, auth_headers, other_car["id"], name="Чужа зима")

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert [t["name"] for t in listed] == ["Зима"]


def test_patch_tire_set_updates_only_given_fields(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    tires = _create_tires(client, auth_headers, car["id"], size="205/55 R16")

    response = client.patch(
        f"/api/tires/{tires['id']}", json={"size": "195/65 R15"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["size"] == "195/65 R15"
    assert body["name"] == "Зима Nokian"
    assert body["season"] == "winter"


def test_patch_tire_set_can_correct_the_install_odometer(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The set already on the car when it was entered has km of its own.

    Installing stamps today's odometer, which would read as «0 км on this
    set» for tires that have run 20 000. The stamp is therefore correctable.
    """
    car = make_car(current_odometer=100_000)
    tires = _create_tires(client, auth_headers, car["id"])
    client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)

    response = client.patch(
        f"/api/tires/{tires['id']}", json={"odometer_at_install": 80_000}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["odometer_at_install"] == 80_000
    assert response.json()["km_on_set"] == 20_000


def test_patch_cannot_mount_a_set_behind_the_install_endpoint(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    summer = _create_tires(client, auth_headers, car["id"], name="Літо", season="summer")
    winter = _create_tires(client, auth_headers, car["id"], name="Зима", season="winter")
    client.post(f"/api/tires/{winter['id']}/install", headers=auth_headers)

    client.patch(f"/api/tires/{summer['id']}", json={"is_installed": True}, headers=auth_headers)

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert [t["is_installed"] for t in listed] == [True, False]
    assert [t["id"] for t in listed] == [winter["id"], summer["id"]]


def test_delete_tire_set_removes_the_row(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    tires = _create_tires(client, auth_headers, car["id"])

    assert client.delete(f"/api/tires/{tires['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json() == []
    assert (
        client.patch(
            f"/api/tires/{tires['id']}", json={"name": "X"}, headers=auth_headers
        ).status_code
        == 404
    )


def test_unknown_season_is_rejected(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/tires",
        json={"name": "Всесезон", "season": "autumn"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_every_season_of_the_plan_is_accepted(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    for season in ("summer", "winter", "all_season"):
        assert _create_tires(client, auth_headers, car["id"], season=season)["season"] == season


# Install: the swap


def test_install_stamps_the_car_odometer(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=100_000)
    tires = _create_tires(client, auth_headers, car["id"])

    response = client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_installed"] is True
    assert body["odometer_at_install"] == 100_000
    assert body["km_on_set"] == 0


def test_install_takes_the_previous_set_off(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=100_000)
    summer = _create_tires(client, auth_headers, car["id"], name="Літо", season="summer")
    winter = _create_tires(client, auth_headers, car["id"], name="Зима", season="winter")

    client.post(f"/api/tires/{summer['id']}/install", headers=auth_headers)
    installed = client.post(f"/api/tires/{winter['id']}/install", headers=auth_headers)
    assert installed.status_code == 200, installed.text

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    by_id = {t["id"]: t for t in listed}
    assert by_id[winter["id"]]["is_installed"] is True
    assert by_id[summer["id"]]["is_installed"] is False
    assert [t["is_installed"] for t in listed].count(True) == 1


def test_install_leaves_another_cars_set_alone(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car(current_odometer=100_000)
    other_car = make_car(brand="Skoda")
    mine = _create_tires(client, auth_headers, car["id"], name="Моя зима")
    theirs = _create_tires(client, auth_headers, other_car["id"], name="Їхня зима")
    client.post(f"/api/tires/{theirs['id']}/install", headers=auth_headers)

    client.post(f"/api/tires/{mine['id']}/install", headers=auth_headers)

    other_listed = client.get(f"/api/cars/{other_car['id']}/tires", headers=auth_headers).json()
    assert other_listed[0]["is_installed"] is True


def test_reinstalling_the_mounted_set_does_not_reset_its_mileage(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """A second «Встановити» on the set already on the car is a no-op.

    Re-stamping would silently zero the km this set has run — the one thing
    the stamp exists to remember.
    """
    car = make_car(current_odometer=100_000)
    tires = _create_tires(client, auth_headers, car["id"])
    client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)
    _set_odometer(db_session_factory, car["id"], 105_000)

    response = client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["odometer_at_install"] == 100_000
    assert response.json()["km_on_set"] == 5_000


def test_install_of_a_missing_set_is_404(client: TestClient, auth_headers: dict) -> None:
    assert client.post("/api/tires/9999/install", headers=auth_headers).status_code == 404


# km_on_set


def test_km_on_set_counts_from_the_install_stamp(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car(current_odometer=100_000)
    tires = _create_tires(client, auth_headers, car["id"])
    client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)
    _set_odometer(db_session_factory, car["id"], 107_500)

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert listed[0]["km_on_set"] == 7_500


def test_km_on_set_is_null_for_a_set_on_the_shelf(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """A set that came off has no km to report: nothing recorded when it did.

    Reporting «odometer - stamp» for it would keep counting kilometres the
    car drove on the other set.
    """
    car = make_car(current_odometer=100_000)
    summer = _create_tires(client, auth_headers, car["id"], name="Літо", season="summer")
    winter = _create_tires(client, auth_headers, car["id"], name="Зима", season="winter")
    client.post(f"/api/tires/{summer['id']}/install", headers=auth_headers)
    _set_odometer(db_session_factory, car["id"], 105_000)
    client.post(f"/api/tires/{winter['id']}/install", headers=auth_headers)

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    by_id = {t["id"]: t for t in listed}
    assert by_id[summer["id"]]["km_on_set"] is None
    assert by_id[winter["id"]]["km_on_set"] == 0


def test_km_on_set_never_goes_negative(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """A corrected-down odometer must read 0 km, not «-3 000 км»."""
    car = make_car(current_odometer=100_000)
    tires = _create_tires(client, auth_headers, car["id"])
    client.post(f"/api/tires/{tires['id']}/install", headers=auth_headers)
    _set_odometer(db_session_factory, car["id"], 97_000)

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert listed[0]["km_on_set"] == 0


def test_km_on_set_is_null_when_the_stamp_is_missing(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car(current_odometer=100_000)
    with db_session_factory() as db:
        db.add(TireSet(car_id=car["id"], name="Легасі", season="winter", is_installed=True))
        db.commit()

    listed = client.get(f"/api/cars/{car['id']}/tires", headers=auth_headers).json()
    assert listed[0]["km_on_set"] is None


# Access


def test_foreign_user_gets_404_everywhere(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    tires = _create_tires(client, auth_headers, car["id"])
    other = make_user(email="intruder@example.com")

    assert client.get(f"/api/cars/{car['id']}/tires", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/cars/{car['id']}/tires",
            json={"name": "X", "season": "winter"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.patch(f"/api/tires/{tires['id']}", json={"name": "X"}, headers=other).status_code
        == 404
    )
    assert client.delete(f"/api/tires/{tires['id']}", headers=other).status_code == 404
    assert client.post(f"/api/tires/{tires['id']}/install", headers=other).status_code == 404


def test_a_viewer_reads_the_tire_sets(
    client: TestClient, auth_headers: dict, make_car, make_user, db_session_factory
) -> None:
    car = make_car()
    _create_tires(client, auth_headers, car["id"])
    viewer = _member(db_session_factory, make_user, car["id"], "viewer")

    response = client.get(f"/api/cars/{car['id']}/tires", headers=viewer)
    assert response.status_code == 200, response.text
    assert [t["name"] for t in response.json()] == ["Зима Nokian"]


def test_an_editor_may_read_but_not_change_the_tire_sets(
    client: TestClient, auth_headers: dict, make_car, make_user, db_session_factory
) -> None:
    """Tire sets are car configuration: the owner decides, the editor logs."""
    car = make_car()
    tires = _create_tires(client, auth_headers, car["id"])
    editor = _member(db_session_factory, make_user, car["id"], "editor")

    assert client.get(f"/api/cars/{car['id']}/tires", headers=editor).status_code == 200
    assert (
        client.post(
            f"/api/cars/{car['id']}/tires",
            json={"name": "X", "season": "winter"},
            headers=editor,
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/tires/{tires['id']}", json={"name": "X"}, headers=editor).status_code
        == 403
    )
    assert client.delete(f"/api/tires/{tires['id']}", headers=editor).status_code == 403
    assert client.post(f"/api/tires/{tires['id']}/install", headers=editor).status_code == 403


def test_deleting_a_car_cascades_its_tire_sets(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car()
    _create_tires(client, auth_headers, car["id"])

    assert client.delete(f"/api/cars/{car['id']}", headers=auth_headers).status_code == 204
    with db_session_factory() as db:
        assert db.execute(select(func.count(TireSet.id))).scalar_one() == 0
