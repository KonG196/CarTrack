"""Unit tests for the bot admin list/stat helpers (read-only, no Telegram)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import sessionmaker

from app.bot import admin as bot_admin
from app.bot import service
from app.models import Car, LogEntry, User


def _make_user(db, email, verified=False, chat=None):
    u = User(email=email, email_verified=verified, telegram_chat_id=chat)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_admin_stats_counts_everything(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        a = _make_user(db, "a@x.com", verified=True, chat="111")
        _make_user(db, "b@x.com", verified=False)
        car = Car(user_id=a.id, brand="VW", model="Golf", year=2015,
                  fuel_type="petrol", current_odometer=100000)
        db.add(car)
        db.commit()
        db.refresh(car)
        db.add(LogEntry(car_id=car.id, type="refuel", odometer=100000,
                        date=dt.date(2024, 1, 1), total_cost=50))
        db.commit()

        stats = service.admin_stats(db)
        assert stats["users"] == 2
        assert stats["verified_users"] == 1
        assert stats["cars"] == 1
        assert stats["log_entries"] == 1
        assert stats["users_with_telegram"] == 1


def test_admin_list_users_is_paged_newest_first(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        for i in range(25):
            _make_user(db, f"u{i:02d}@x.com")
        assert service.admin_count_users(db) == 25
        page1 = service.admin_list_users(db, offset=0, limit=20)
        page2 = service.admin_list_users(db, offset=20, limit=20)
        assert len(page1) == 20
        assert len(page2) == 5
        assert page1[0].email == "u24@x.com"


def test_admin_list_cars_is_paged(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner = _make_user(db, "owner@x.com")
        for i in range(21):
            db.add(Car(user_id=owner.id, brand="B", model=f"M{i}", year=2000,
                       fuel_type="petrol", current_odometer=0))
        db.commit()
        assert service.admin_count_cars(db) == 21
        assert len(service.admin_list_cars(db, offset=0, limit=20)) == 20
        assert len(service.admin_list_cars(db, offset=20, limit=20)) == 1


def test_admin_user_car_count(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner = _make_user(db, "o@x.com")
        other = _make_user(db, "p@x.com")
        for _ in range(3):
            db.add(Car(user_id=owner.id, brand="B", model="M", year=2000,
                       fuel_type="petrol", current_odometer=0))
        db.commit()
        assert service.admin_user_car_count(db, owner.id) == 3
        assert service.admin_user_car_count(db, other.id) == 0


def test_admin_mode_toggle_is_per_chat() -> None:
    bot_admin.set_admin_mode(999, True)
    assert bot_admin.is_admin_mode(999) is True
    assert bot_admin.is_admin_mode(1000) is False
    bot_admin.set_admin_mode(999, False)
    assert bot_admin.is_admin_mode(999) is False


def test_format_users_hides_sensitive_and_lists_rows(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        a = _make_user(db, "person@x.com", verified=True, chat="55")
        a.hashed_password = "SECRET-HASH"
        a.verify_code_hash = "SECRET-CODE"
        db.commit()
        users = service.admin_list_users(db, 0, 20)
        text = bot_admin.format_users(db, users, page=1, pages=1, total=1, lang="en")
        assert "person@x.com" in text
        assert "SECRET-HASH" not in text
        assert "SECRET-CODE" not in text


def test_format_cars_renders_label(db_session_factory: sessionmaker) -> None:
    with db_session_factory() as db:
        owner = _make_user(db, "owner@x.com")
        db.add(Car(user_id=owner.id, brand="VW", model="Golf", year=2015,
                   fuel_type="petrol", current_odometer=123456))
        db.commit()
        cars = service.admin_list_cars(db, 0, 20)
        text = bot_admin.format_cars(cars, page=1, pages=1, total=1, lang="en")
        assert "VW" in text and "Golf" in text
        assert "123456" in text


def test_page_keyboard_has_nav_callbacks() -> None:
    kb = bot_admin.page_keyboard("users", page=1, pages=3, lang="en")
    all_data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "adm:users:1" in all_data  # next from page 1 → target page 2 (0-based index 1)
    assert "adm:menu:0" in all_data


def test_page_keyboard_first_page_has_no_prev() -> None:
    kb = bot_admin.page_keyboard("cars", page=1, pages=3, lang="en")
    all_data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert not any(d.startswith("adm:cars:") and d.endswith(":-1") for d in all_data)
    # page 1 → prev would point to index -1, which must never be produced
    assert "adm:cars:0" not in all_data  # no prev button on first page


def test_format_stats_shows_all_counts() -> None:
    stats = {"users": 5, "verified_users": 3, "cars": 4, "log_entries": 99, "users_with_telegram": 2}
    text = bot_admin.format_stats(stats, lang="en")
    assert "5" in text and "3" in text and "4" in text and "99" in text and "2" in text
