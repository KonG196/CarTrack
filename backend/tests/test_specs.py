"""Car cheat-sheet tests: spec CRUD, ownership, and the Golf 7 preset."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import CarSpec
from app.services.spec_presets import SPEC_PRESETS

TORQUE = "Моменти затяжки"
FLUIDS = "Рідини та обʼєми"
APPROVALS = "Допуски"
OTHER = "Інше"


def _create_spec(client: TestClient, headers: dict, car_id: int, **overrides) -> dict:
    payload = {"category": TORQUE, "name": "Колісні болти", "value": "120 Нм"}
    payload.update(overrides)
    response = client.post(f"/api/cars/{car_id}/specs", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# CRUD


def test_create_spec_returns_the_stored_row(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    spec = _create_spec(client, auth_headers, car["id"])
    assert spec["car_id"] == car["id"]
    assert spec["category"] == TORQUE
    assert spec["name"] == "Колісні болти"
    assert spec["value"] == "120 Нм"
    assert spec["sort_order"] == 0


def test_list_specs_is_empty_for_a_new_car(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_specs_orders_by_category_then_sort_order(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    # Deliberately inserted out of order: the API owns the display order.
    _create_spec(client, auth_headers, car["id"], category=OTHER, name="Код двигуна", value="CXXB")
    _create_spec(
        client, auth_headers, car["id"], category=TORQUE, name="Пробка", value="30 Нм", sort_order=2
    )
    _create_spec(
        client, auth_headers, car["id"], category=TORQUE, name="Болти", value="120 Нм", sort_order=1
    )
    _create_spec(client, auth_headers, car["id"], category=FLUIDS, name="Олива", value="4.6 л")

    listed = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json()
    assert [(s["category"], s["name"]) for s in listed] == [
        (TORQUE, "Болти"),
        (TORQUE, "Пробка"),
        (FLUIDS, "Олива"),
        (OTHER, "Код двигуна"),
    ]


def test_patch_spec_updates_only_given_fields(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    spec = _create_spec(client, auth_headers, car["id"])

    response = client.patch(
        f"/api/specs/{spec['id']}", json={"value": "140 Нм"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] == "140 Нм"
    assert body["name"] == "Колісні болти"
    assert body["category"] == TORQUE


def test_delete_spec_removes_the_row(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    spec = _create_spec(client, auth_headers, car["id"])

    assert client.delete(f"/api/specs/{spec['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json() == []
    assert (
        client.patch(
            f"/api/specs/{spec['id']}", json={"value": "x"}, headers=auth_headers
        ).status_code
        == 404
    )


def test_a_retired_category_still_lists_rather_than_500(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    """A category dropped from SPEC_CATEGORIES must not brick an existing sheet."""
    car = make_car()
    _create_spec(client, auth_headers, car["id"])
    with db_session_factory() as db:
        db.add(CarSpec(car_id=car["id"], category="Знята рубрика", name="X", value="Y"))
        db.commit()

    response = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers)
    assert response.status_code == 200, response.text
    # The known category still leads; the stranger is tolerated at the end.
    assert [s["name"] for s in response.json()] == ["Колісні болти", "X"]


def test_unknown_category_is_rejected(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/specs",
        json={"category": "Вигадана", "name": "X", "value": "Y"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# Ownership


def test_foreign_user_gets_404_everywhere(
    client: TestClient, auth_headers: dict, make_car, make_user
) -> None:
    car = make_car()
    spec = _create_spec(client, auth_headers, car["id"])
    other = make_user(email="intruder@example.com")

    assert client.get(f"/api/cars/{car['id']}/specs", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/cars/{car['id']}/specs",
            json={"category": TORQUE, "name": "X", "value": "Y"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.patch(f"/api/specs/{spec['id']}", json={"value": "X"}, headers=other).status_code
        == 404
    )
    assert client.delete(f"/api/specs/{spec['id']}", headers=other).status_code == 404


def test_deleting_a_car_cascades_its_specs(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    car = make_car()
    _create_spec(client, auth_headers, car["id"])

    assert client.delete(f"/api/cars/{car['id']}", headers=auth_headers).status_code == 204
    with db_session_factory() as db:
        assert db.execute(select(func.count(CarSpec.id))).scalar_one() == 0


# Preset


def test_preset_creates_exactly_nine_rows(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    assert len(response.json()) == 9
    assert len(client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json()) == 9


def test_preset_carries_the_service_passport_values(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The preset is the owner's real Golf 7 passport, copied verbatim."""
    car = make_car()
    client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )
    listed = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json()

    assert [(s["category"], s["name"], s["value"]) for s in listed] == [
        (TORQUE, "Wheel bolts", "120 N·m"),
        (TORQUE, "Oil drain plug", "30 N·m"),
        (FLUIDS, "Engine oil", "~4.6 L"),
        (FLUIDS, "Antifreeze", "G13"),
        (APPROVALS, "Oil approval", "VW 507.00"),
        (APPROVALS, "Fuel", "Diesel Euro-5"),
        (OTHER, "Engine code", "CXXB (EA288)"),
        (OTHER, "Gearbox code", "RTD (5-speed manual)"),
        (OTHER, "Paint code", "LI7F (Urano Gray)"),
    ]


def test_preset_table_has_no_invented_rows() -> None:
    assert len(SPEC_PRESETS["golf7_16tdi"]) == 9


def test_preset_is_idempotent_per_car_category_name(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    first = client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    ).json()

    second = client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )
    assert second.status_code == 201, second.text
    assert len(second.json()) == 9
    assert [s["id"] for s in second.json()] == [s["id"] for s in first]


def test_preset_never_overwrites_an_edited_value(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """A preset row is a starting point; a re-run must not undo an edit."""
    car = make_car()
    client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )
    listed = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json()
    bolts = next(s for s in listed if s["name"] == "Wheel bolts")
    client.patch(f"/api/specs/{bolts['id']}", json={"value": "140 N·m"}, headers=auth_headers)

    client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )

    again = client.get(f"/api/cars/{car['id']}/specs", headers=auth_headers).json()
    assert next(s for s in again if s["name"] == "Wheel bolts")["value"] == "140 N·m"
    assert len(again) == 9


def test_preset_fills_only_the_gaps(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    _create_spec(client, auth_headers, car["id"], category=TORQUE, name="Wheel bolts", value="90 N·m")

    response = client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "golf7_16tdi"}, headers=auth_headers
    )
    assert len(response.json()) == 9
    values = {s["name"]: s["value"] for s in response.json()}
    assert values["Wheel bolts"] == "90 N·m"  # the user's own row survives


def test_unknown_preset_key_404(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car()
    response = client.post(
        f"/api/cars/{car['id']}/specs/preset", params={"key": "tesla_plaid"}, headers=auth_headers
    )
    assert response.status_code == 404
