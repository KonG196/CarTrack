"""Car imagery: Wikimedia CC0 photo lookup (cached, best-effort) + marque-logo
fallback resolution."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import sessionmaker

from app.models import Car, User
from app.services import car_image


def _car(sf: sessionmaker, brand="Volkswagen") -> Car:
    with sf() as db:
        u = User(email="c@example.com", hashed_password="x")
        db.add(u)
        db.flush()
        car = Car(
            user_id=u.id, brand=brand, model="Golf", year=2018,
            fuel_type="petrol", current_odometer=1000,
        )
        db.add(car)
        db.commit()
        db.refresh(car)
        db.expunge(car)
        return car


# ── photo lookup + cache ─────────────────────────────────────────────────────


def test_fetches_and_caches(monkeypatch, db_session_factory):
    calls = {"n": 0}

    def fake_resolve(car):
        calls["n"] += 1
        return "https://upload.wikimedia.org/x/golf.jpg"

    monkeypatch.setattr(car_image, "_resolve", fake_resolve)

    car = _car(db_session_factory)
    with db_session_factory() as db:
        car = db.merge(car)
        url = car_image.get_car_image(db, car)
        assert url == "https://upload.wikimedia.org/x/golf.jpg"
        assert car.image_url == url and car.image_expires_at is not None
        # Fresh cache → no second resolve.
        car_image.get_car_image(db, car)
        assert calls["n"] == 1


def test_no_photo_latches_missing(monkeypatch, db_session_factory):
    monkeypatch.setattr(car_image, "_resolve", lambda car: None)
    car = _car(db_session_factory)
    with db_session_factory() as db:
        car = db.merge(car)
        assert car_image.get_car_image(db, car) is None
        assert car.image_missing is True
        called = {"n": 0}
        monkeypatch.setattr(
            car_image, "_resolve", lambda car: called.__setitem__("n", 1)
        )
        assert car_image.get_car_image(db, car) is None
        assert called["n"] == 0  # not re-probed within the recheck window


def test_expired_cache_refetches(monkeypatch, db_session_factory):
    car = _car(db_session_factory)
    with db_session_factory() as db:
        car = db.merge(car)
        car.image_url = "https://upload.wikimedia.org/x/old.jpg"
        car.image_expires_at = dt.datetime(2000, 1, 1)
        db.commit()
        monkeypatch.setattr(car_image, "_resolve", lambda c: "https://upload.wikimedia.org/x/new.jpg")
        assert car_image.get_car_image(db, car).endswith("new.jpg")


# ── marque-logo fallback ─────────────────────────────────────────────────────


def test_logo_url_for_known_brands():
    assert car_image.brand_logo_url("Volkswagen").endswith("/volkswagen.png")
    assert car_image.brand_logo_url("Mercedes-Benz").endswith("/mercedes-benz.png")
    assert car_image.brand_logo_url("Alfa Romeo").endswith("/alfa-romeo.png")
    # Case / spacing normalised.
    assert car_image.brand_logo_url("  toyota ").endswith("/toyota.png")


def test_logo_url_none_for_unknown_or_empty():
    assert car_image.brand_logo_url("Definitely Not A Car Brand XYZ") is None
    assert car_image.brand_logo_url("") is None
    assert car_image.brand_logo_url(None) is None


def test_slugify_brand():
    assert car_image._slugify_brand("Mercedes-Benz") == "mercedes-benz"
    assert car_image._slugify_brand("Alfa Romeo") == "alfa-romeo"
    assert car_image._slugify_brand("Rolls  Royce") == "rolls-royce"


def test_logo_url_cyrillic_marques():
    # Post-Soviet brands written in Cyrillic map to their Latin dataset slug.
    assert car_image.brand_logo_url("ЗАЗ").endswith("/zaz.png")
    assert car_image.brand_logo_url("ГАЗ").endswith("/gaz.png")
    assert car_image.brand_logo_url("ВАЗ").endswith("/lada.png")
    assert car_image.brand_logo_url("Таврія").endswith("/zaz.png")
    # Uses the lighter thumb, not the optimized asset.
    assert "/logos/thumb/" in car_image.brand_logo_url("MAN")


# ── query building: model cleanup, generation, year ──────────────────────────


def test_clean_model_strips_trim_keeps_model():
    # First token always kept (may be the model, e.g. "3" in "3 Series").
    assert car_image._clean_model("3 Series 320d") == "3 Series"
    assert car_image._clean_model("1 Series 118i") == "1 Series"
    assert car_image._clean_model("Gls 350") == "Gls"
    assert car_image._clean_model("Passat 2.0") == "Passat"
    assert car_image._clean_model("A4 2.0 TDI") == "A4"
    assert car_image._clean_model("GLE 400 d") == "GLE"
    # Plain models are left alone.
    assert car_image._clean_model("Golf") == "Golf"
    assert car_image._clean_model("L200") == "L200"
    assert car_image._clean_model("C-Class") == "C-Class"


def test_generation_terms():
    class C:
        def __init__(self, g):
            self.generation = g

    assert car_image._generation_terms(C("7 (BA5)")) == ["Mk7", "VII"]
    assert car_image._generation_terms(C("B7")) == ["B7"]
    assert car_image._generation_terms(C("W205")) == ["W205"]
    assert car_image._generation_terms(C("G20")) == ["G20"]
    assert car_image._generation_terms(C("")) == []
    assert car_image._generation_terms(C(None)) == []


def test_title_year():
    assert car_image._title_year("bmw 320d (e90) front poznan 2011.jpg") == 2011
    assert car_image._title_year("2013 kia sportage sl.jpg") == 2013
    assert car_image._title_year("volkswagen golf.jpg") is None
