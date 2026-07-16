"""Public QR passport: token minting, the tokenless read, and revocation."""

from fastapi.testclient import TestClient


def _set_passport_fields(client: TestClient, headers: dict, car_id: int) -> None:
    response = client.patch(
        f"/api/cars/{car_id}",
        json={
            "contact_phone": "067 000 00 00",
            "insurance_number": "AX1234567",
            "insurance_until": "2027-03-01",
            "tire_pressure": "2.2/2.4 бар",
            "fuel_approval": "Дизель, EN590",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_mint_read_and_revoke(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car(vin="WVWZZZAUZHP541983", plate="BC3940PO")
    _set_passport_fields(client, auth_headers, car["id"])

    minted = client.post(f"/api/cars/{car['id']}/passport-token", headers=auth_headers)
    assert minted.status_code == 200, minted.text
    body = minted.json()
    token = body["token"]
    assert len(token) == 32
    assert token in body["url"]
    assert body["qr_svg"].lstrip().startswith("<svg")

    # Idempotent: the second mint returns the same link, so a printed QR keeps working.
    again = client.post(f"/api/cars/{car['id']}/passport-token", headers=auth_headers)
    assert again.json()["token"] == token

    # Tokenless public read shows the passport fields, VIN included.
    public = client.get(f"/api/public/cars/{token}")
    assert public.status_code == 200, public.text
    passport = public.json()
    assert passport["vin"] == "WVWZZZAUZHP541983"
    assert passport["plate"] == "BC3940PO"
    assert passport["contact_phone"] == "067 000 00 00"
    assert passport["fuel_approval"] == "Дизель, EN590"
    # It never leaks anything but the passport fields.
    assert "your_role" not in passport
    assert "scratchpad" not in passport

    # Revoking kills the link.
    revoked = client.delete(f"/api/cars/{car['id']}/passport-token", headers=auth_headers)
    assert revoked.status_code == 204
    assert client.get(f"/api/public/cars/{token}").status_code == 404


def test_regenerate_replaces_the_token(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    first = client.post(
        f"/api/cars/{car['id']}/passport-token", headers=auth_headers
    ).json()["token"]
    second = client.post(
        f"/api/cars/{car['id']}/passport-token",
        params={"regenerate": True},
        headers=auth_headers,
    ).json()["token"]
    assert second != first
    assert client.get(f"/api/public/cars/{first}").status_code == 404
    assert client.get(f"/api/public/cars/{second}").status_code == 200


def test_public_unknown_token_is_404(client: TestClient) -> None:
    assert client.get("/api/public/cars/nope").status_code == 404


def test_mint_is_owner_only(
    client: TestClient, auth_headers: dict, make_car, make_user, db_session_factory
) -> None:
    from app.models import CarMember, User
    from sqlalchemy import select

    car = make_car()
    viewer = make_user("viewer@example.com")
    with db_session_factory() as db:
        user = db.execute(select(User).where(User.email == "viewer@example.com")).scalar_one()
        db.add(CarMember(car_id=car["id"], user_id=user.id, role="viewer"))
        db.commit()
    response = client.post(f"/api/cars/{car['id']}/passport-token", headers=viewer)
    assert response.status_code in (403, 404)
