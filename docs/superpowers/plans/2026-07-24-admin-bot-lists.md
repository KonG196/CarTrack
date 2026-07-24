# Admin Bot Lists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin-only commands to the main Telegram bot that let the owner page through users, cars, and DB stats (20 per page), gated behind a `/admin` mode toggle so the same account can still keep its own car logbook.

**Architecture:** The admin bot (`@kapot_tracker_admin_bot`) is outbound-only (a plain `httpx.post`), so it cannot receive commands. Instead we add the commands to the existing aiogram polling bot in `app/bot/`. A `/admin` command toggles an in-memory "admin mode" flag for the owner's chat (gated by `User.is_superadmin`); while on, it shows an inline menu (Users / Cars / Stats). Each list is rendered into a single message that is edited in place by ◀/▶ callback buttons, paging 20 rows at a time. Every query reuses the read-only patterns already proven in `app/routers/admin.py`, and never selects sensitive columns (`hashed_password`, `verify_code_hash`, `reset_code_hash`, `token_version`).

**Tech Stack:** Python 3, aiogram v3, SQLAlchemy 2.0, existing `app.i18n` catalog.

## Global Constraints

- **NO push / deploy without explicit per-action approval.** Commit locally only; wait for a fresh "push"/"deploy" before touching `origin` or prod. (Vercel is frontend-only and untouched here; this is a backend/bot change.)
- **Git author MUST be `KonG196 <maks060691@gmail.com>`.** NEVER add `Co-Authored-By` or any AI attribution to commits.
- **No Ukrainian comments in NEW backend code.** Code comments and docstrings in English. (User-facing strings are bilingual via `app.i18n`, which is fine.)
- **Never show sensitive columns** in any admin output: `hashed_password`, `verify_code_hash`, `reset_code_hash`, `reset_code_expires_at`, `verify_code_expires_at`, `token_version`, and the reset/verify attempt counters.
- **Gate every admin command and callback by `user.is_superadmin`.** A non-admin (or unlinked) chat that sends `/admin` or forges an `adm:` callback must get the plain "admin only" rejection and nothing else — no data, no confirmation the command exists.
- **Page size is exactly 20.** Defined once as a module constant `_ADMIN_PAGE = 20`.
- **In-memory toggle only** — no new DB column, no migration. State resets to "user mode" on bot restart; re-running `/admin` turns it back on.
- Parallel Claude sessions edit this repo. Re-read each file immediately before editing, and `git add` ONLY the files this plan touches.

---

## File Structure

- `backend/app/bot/service.py` — **add** read-only admin query helpers (paged users, paged cars, global stats). Pure DB functions, no aiogram types. This is where all SQL lives so handlers stay thin.
- `backend/app/bot/admin.py` — **new file** — the admin-mode state (in-memory set of admin chat ids), the gate helper, the inline-keyboard builders, and the message-body formatters. Keeps the admin surface isolated from the 1300-line `handlers.py`.
- `backend/app/bot/handlers.py` — **add** the `/admin` command handler and the `adm:` callback handler; import from `app/bot/admin.py` and `service.py`.
- `backend/app/bot/main.py` — **add** the `/admin` entry to the Telegram command menu (`bot_commands`).
- `backend/app/i18n.py` — **add** the `bot.cmd.admin` menu label and all `bot.admin.*` message strings (EN + UK).
- `backend/tests/bot/test_admin_lists.py` — **new file** — unit tests for the service helpers and the gate (no live Telegram; call functions directly with a seeded in-memory DB).

---

## Task 1: Admin query helpers in the service layer

**Files:**
- Modify: `backend/app/bot/service.py` (append new functions at end of file)
- Test: `backend/tests/bot/test_admin_lists.py`

**Interfaces:**
- Consumes: `SessionLocal`, `User`, `Car`, `LogEntry` (already imported in `service.py`; verify and add any missing import).
- Produces:
  - `admin_count_users(db: Session) -> int`
  - `admin_list_users(db: Session, offset: int, limit: int) -> list[User]` — newest first (`User.created_at.desc()`).
  - `admin_count_cars(db: Session) -> int`
  - `admin_list_cars(db: Session, offset: int, limit: int) -> list[Car]` — newest first (`Car.created_at.desc()`).
  - `admin_user_car_count(db: Session, user_id: int) -> int`
  - `admin_stats(db: Session) -> dict` with keys: `users`, `verified_users`, `cars`, `log_entries`, `users_with_telegram`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/bot/test_admin_lists.py`:

```python
"""Unit tests for the bot admin list/stat helpers."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Car, LogEntry, User
from app.bot import service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _make_user(db, email, verified=False, chat=None):
    u = User(email=email, email_verified=verified, telegram_chat_id=chat)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_admin_stats_counts_everything(db):
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


def test_admin_list_users_is_paged_newest_first(db):
    for i in range(25):
        _make_user(db, f"u{i:02d}@x.com")
    assert service.admin_count_users(db) == 25
    page1 = service.admin_list_users(db, offset=0, limit=20)
    page2 = service.admin_list_users(db, offset=20, limit=20)
    assert len(page1) == 20
    assert len(page2) == 5
    # Newest first: the last-created user (u24) leads page 1.
    assert page1[0].email == "u24@x.com"


def test_admin_list_cars_is_paged(db):
    owner = _make_user(db, "owner@x.com")
    for i in range(21):
        db.add(Car(user_id=owner.id, brand="B", model=f"M{i}", year=2000,
                   fuel_type="petrol", current_odometer=0))
    db.commit()
    assert service.admin_count_cars(db) == 21
    assert len(service.admin_list_cars(db, offset=0, limit=20)) == 20
    assert len(service.admin_list_cars(db, offset=20, limit=20)) == 1


def test_admin_user_car_count(db):
    owner = _make_user(db, "o@x.com")
    other = _make_user(db, "p@x.com")
    for _ in range(3):
        db.add(Car(user_id=owner.id, brand="B", model="M", year=2000,
                   fuel_type="petrol", current_odometer=0))
    db.commit()
    assert service.admin_user_car_count(db, owner.id) == 3
    assert service.admin_user_car_count(db, other.id) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/bot/test_admin_lists.py -v`
Expected: FAIL with `AttributeError: module 'app.bot.service' has no attribute 'admin_stats'` (and the other helpers).

- [ ] **Step 3: Write the implementation**

First confirm the imports at the top of `app/bot/service.py` include `func` from sqlalchemy and the models. If `func` is not imported, add it to the existing sqlalchemy import line (e.g. `from sqlalchemy import func, select`). Confirm `LogEntry` is importable from `app.models` (add to the models import if absent).

Append to the end of `backend/app/bot/service.py`:

```python
# ── Admin read-only helpers ──────────────────────────────────────────────
# Used by the bot's /admin mode. Read-only, newest-first, and they never
# select sensitive columns — the caller formats only safe fields.


def admin_count_users(db: Session) -> int:
    return db.scalar(select(func.count(User.id))) or 0


def admin_list_users(db: Session, offset: int, limit: int) -> list[User]:
    return list(
        db.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        .scalars()
        .all()
    )


def admin_count_cars(db: Session) -> int:
    return db.scalar(select(func.count(Car.id))) or 0


def admin_list_cars(db: Session, offset: int, limit: int) -> list[Car]:
    return list(
        db.execute(
            select(Car).order_by(Car.created_at.desc()).offset(offset).limit(limit)
        )
        .scalars()
        .all()
    )


def admin_user_car_count(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count(Car.id)).where(Car.user_id == user_id)) or 0


def admin_stats(db: Session) -> dict:
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "verified_users": db.scalar(
            select(func.count(User.id)).where(User.email_verified.is_(True))
        )
        or 0,
        "cars": db.scalar(select(func.count(Car.id))) or 0,
        "log_entries": db.scalar(select(func.count(LogEntry.id))) or 0,
        "users_with_telegram": db.scalar(
            select(func.count(User.id)).where(User.telegram_chat_id.is_not(None))
        )
        or 0,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/bot/test_admin_lists.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/bot/service.py backend/tests/bot/test_admin_lists.py
git commit -m "feat(bot): admin read-only list/stat query helpers"
```

---

## Task 2: i18n strings for the admin surface

**Files:**
- Modify: `backend/app/i18n.py` (add keys into the `MESSAGES` dict, in the `bot.cmd.*` and `bot.*` regions, keeping alphabetical order within each group)

**Interfaces:**
- Produces these i18n keys (each with `en` + `uk`), consumed by Tasks 3–4:
  - `bot.cmd.admin`
  - `bot.admin.notAdmin`
  - `bot.admin.menuTitle`
  - `bot.admin.on`
  - `bot.admin.off`
  - `bot.admin.btnUsers`, `bot.admin.btnCars`, `bot.admin.btnStats`, `bot.admin.btnClose`
  - `bot.admin.usersTitle`, `bot.admin.carsTitle`
  - `bot.admin.userRow`, `bot.admin.carRow`
  - `bot.admin.pageFooter`
  - `bot.admin.statsTitle`, `bot.admin.statsBody`
  - `bot.admin.empty`
  - `bot.admin.prev`, `bot.admin.next`
  - `bot.admin.closed`

- [ ] **Step 1: Add the command-menu label**

In `app/i18n.py`, next to the existing `"bot.cmd.backup"` entry (around line 286), add (alphabetical — `admin` before `backup`):

```python
    "bot.cmd.admin": {"en": "Admin mode (owner only)", "uk": "Режим адміна (лише власник)"},
```

- [ ] **Step 2: Add the admin message strings**

Add a new block (place it just before the first `"bot.cmd."` entry so the `bot.admin.*` group sits alphabetically ahead of `bot.cmd.*`). Placeholders must be identical across languages.

```python
    # ── Bot: admin mode (owner-only lists) ──
    "bot.admin.notAdmin": {
        "en": "This command is available to the owner only.",
        "uk": "Ця команда доступна лише власнику.",
    },
    "bot.admin.on": {
        "en": "Admin mode ON. Your logbook commands still work as usual.",
        "uk": "Режим адміна УВІМКНЕНО. Команди журналу працюють як завжди.",
    },
    "bot.admin.off": {
        "en": "Admin mode OFF.",
        "uk": "Режим адміна ВИМКНЕНО.",
    },
    "bot.admin.menuTitle": {
        "en": "Admin — what do you want to see?",
        "uk": "Адмін — що показати?",
    },
    "bot.admin.btnUsers": {"en": "👤 Users", "uk": "👤 Користувачі"},
    "bot.admin.btnCars": {"en": "🚗 Cars", "uk": "🚗 Авто"},
    "bot.admin.btnStats": {"en": "📊 Stats", "uk": "📊 Статистика"},
    "bot.admin.btnClose": {"en": "✖ Close", "uk": "✖ Закрити"},
    "bot.admin.usersTitle": {"en": "👤 Users", "uk": "👤 Користувачі"},
    "bot.admin.carsTitle": {"en": "🚗 Cars", "uk": "🚗 Авто"},
    "bot.admin.userRow": {
        "en": "#{id} {email} · {provider}{verified} · 🚗{cars} · {joined}",
        "uk": "#{id} {email} · {provider}{verified} · 🚗{cars} · {joined}",
    },
    "bot.admin.carRow": {
        "en": "#{id} {label} · {year} · {odo} km · owner #{owner}",
        "uk": "#{id} {label} · {year} · {odo} км · власник #{owner}",
    },
    "bot.admin.pageFooter": {
        "en": "Page {page}/{pages} · {total} total",
        "uk": "Стор. {page}/{pages} · всього {total}",
    },
    "bot.admin.statsTitle": {"en": "📊 Stats", "uk": "📊 Статистика"},
    "bot.admin.statsBody": {
        "en": (
            "Users: {users} ({verified} verified)\n"
            "Linked to Telegram: {telegram}\n"
            "Cars: {cars}\n"
            "Log entries: {logs}"
        ),
        "uk": (
            "Користувачі: {users} ({verified} підтверджено)\n"
            "Прив'язано до Telegram: {telegram}\n"
            "Авто: {cars}\n"
            "Записи журналу: {logs}"
        ),
    },
    "bot.admin.empty": {"en": "Nothing here yet.", "uk": "Тут поки порожньо."},
    "bot.admin.prev": {"en": "◀", "uk": "◀"},
    "bot.admin.next": {"en": "▶", "uk": "▶"},
    "bot.admin.closed": {"en": "Closed.", "uk": "Закрито."},
```

- [ ] **Step 3: Verify the catalog still imports**

Run: `cd backend && python -c "from app.i18n import t; print(t('bot.admin.on', 'uk')); print(t('bot.cmd.admin', 'en'))"`
Expected: prints the Ukrainian "Режим адміна УВІМКНЕНО…" line and the English "Admin mode (owner only)".

- [ ] **Step 4: Commit**

```bash
git add backend/app/i18n.py
git commit -m "i18n(bot): strings for admin mode and paginated lists"
```

---

## Task 3: Admin module — state, gate, keyboards, formatters

**Files:**
- Create: `backend/app/bot/admin.py`
- Test: extend `backend/tests/bot/test_admin_lists.py`

**Interfaces:**
- Consumes: `app.i18n.t`, `app.bot.service` helpers from Task 1, aiogram `InlineKeyboardButton`/`InlineKeyboardMarkup`, `User`/`Car` from `app.models`.
- Produces:
  - `_ADMIN_PAGE = 20` (module constant)
  - `is_admin_mode(chat_id: int) -> bool`
  - `set_admin_mode(chat_id: int, on: bool) -> None`
  - `menu_keyboard(lang: str) -> InlineKeyboardMarkup` — the Users/Cars/Stats/Close buttons.
  - `page_keyboard(kind: str, page: int, pages: int, lang: str) -> InlineKeyboardMarkup` — ◀/▶ nav with a "back to menu" button; callback data `adm:{kind}:{page}`, `adm:menu:0`, `adm:close:0`.
  - `format_users(db, users, page, pages, total, lang) -> str`
  - `format_cars(cars, page, pages, total, lang) -> str`
  - `format_stats(stats, lang) -> str`

**Interface note:** callback data format is `adm:<kind>:<page>` where `<kind>` ∈ {`users`, `cars`, `stats`, `menu`, `close`} and `<page>` is a 0-based page index (0 for stats/menu/close). Telegram caps callback data at 64 bytes — this stays well under.

- [ ] **Step 1: Write the failing test (formatters + state)**

Append to `backend/tests/bot/test_admin_lists.py`:

```python
from app.bot import admin as bot_admin


def test_admin_mode_toggle_is_per_chat():
    bot_admin.set_admin_mode(999, True)
    assert bot_admin.is_admin_mode(999) is True
    assert bot_admin.is_admin_mode(1000) is False
    bot_admin.set_admin_mode(999, False)
    assert bot_admin.is_admin_mode(999) is False


def test_format_users_hides_sensitive_and_lists_rows(db):
    a = _make_user(db, "person@x.com", verified=True, chat="55")
    a.hashed_password = "SECRET-HASH"
    a.verify_code_hash = "SECRET-CODE"
    db.commit()
    users = service.admin_list_users(db, 0, 20)
    text = bot_admin.format_users(db, users, page=1, pages=1, total=1, lang="en")
    assert "person@x.com" in text
    assert "SECRET-HASH" not in text
    assert "SECRET-CODE" not in text


def test_format_cars_renders_label(db):
    owner = _make_user(db, "owner@x.com")
    db.add(Car(user_id=owner.id, brand="VW", model="Golf", year=2015,
               fuel_type="petrol", current_odometer=123456))
    db.commit()
    cars = service.admin_list_cars(db, 0, 20)
    text = bot_admin.format_cars(cars, page=1, pages=1, total=1, lang="en")
    assert "VW" in text and "Golf" in text
    assert "123456" in text or "123 456" in text


def test_page_keyboard_has_nav_callbacks():
    kb = bot_admin.page_keyboard("users", page=1, pages=3, lang="en")
    all_data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "adm:users:2" in all_data  # next → page index 2
    assert "adm:menu:0" in all_data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/bot/test_admin_lists.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.bot.admin'`.

- [ ] **Step 3: Write `backend/app/bot/admin.py`**

```python
"""Bot admin mode: owner-only paginated views of users, cars and DB stats.

The admin Telegram integration elsewhere is outbound-only, so these live in the
main user bot instead. Access is gated by ``User.is_superadmin`` in the handler;
this module only holds the (in-memory) mode flag, the inline keyboards, and the
message formatters. Formatters take already-fetched, safe objects and never
read sensitive columns.
"""

from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import Session

from app.bot import service
from app.i18n import t
from app.models import Car, User

# Rows per page. One definition, used everywhere.
_ADMIN_PAGE = 20

# Chats currently in admin mode. In-memory on purpose: the flag is trivial to
# rebuild (send /admin again) and resets safely to "off" on restart.
_admin_chats: set[int] = set()


def is_admin_mode(chat_id: int) -> bool:
    return chat_id in _admin_chats


def set_admin_mode(chat_id: int, on: bool) -> None:
    if on:
        _admin_chats.add(chat_id)
    else:
        _admin_chats.discard(chat_id)


def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("bot.admin.btnUsers", lang), callback_data="adm:users:0"
                ),
                InlineKeyboardButton(
                    text=t("bot.admin.btnCars", lang), callback_data="adm:cars:0"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("bot.admin.btnStats", lang), callback_data="adm:stats:0"
                ),
                InlineKeyboardButton(
                    text=t("bot.admin.btnClose", lang), callback_data="adm:close:0"
                ),
            ],
        ]
    )


def page_keyboard(kind: str, page: int, pages: int, lang: str) -> InlineKeyboardMarkup:
    """Nav row for a list: ◀ (if not first), ▶ (if not last), then a menu button.

    ``page`` is 1-based here (as shown to the user); callback data carries the
    0-based index of the target page.
    """
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("bot.admin.prev", lang),
                callback_data=f"adm:{kind}:{page - 2}",
            )
        )
    if page < pages:
        nav.append(
            InlineKeyboardButton(
                text=t("bot.admin.next", lang),
                callback_data=f"adm:{kind}:{page}",
            )
        )
    rows: list[list[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=t("bot.admin.menuTitle", lang), callback_data="adm:menu:0"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pages(total: int) -> int:
    """How many pages ``total`` rows span (at least 1, so an empty list shows 1/1)."""
    return max(1, (total + _ADMIN_PAGE - 1) // _ADMIN_PAGE)


def _footer(page: int, pages: int, total: int, lang: str) -> str:
    return t("bot.admin.pageFooter", lang, page=page, pages=pages, total=total)


def format_users(
    db: Session,
    users: list[User],
    page: int,
    pages: int,
    total: int,
    lang: str,
) -> str:
    title = t("bot.admin.usersTitle", lang)
    if not users:
        return f"{title}\n\n{t('bot.admin.empty', lang)}"
    lines = []
    for u in users:
        verified = " ✅" if u.email_verified else ""
        provider = u.auth_provider or "password"
        cars = service.admin_user_car_count(db, u.id)
        joined = u.created_at.date().isoformat() if u.created_at else "—"
        lines.append(
            t(
                "bot.admin.userRow",
                lang,
                id=u.id,
                email=u.email,
                provider=provider,
                verified=verified,
                cars=cars,
                joined=joined,
            )
        )
    body = "\n".join(lines)
    return f"{title}\n\n{body}\n\n{_footer(page, pages, total, lang)}"


def format_cars(
    cars: list[Car],
    page: int,
    pages: int,
    total: int,
    lang: str,
) -> str:
    title = t("bot.admin.carsTitle", lang)
    if not cars:
        return f"{title}\n\n{t('bot.admin.empty', lang)}"
    lines = []
    for c in cars:
        label = " ".join(part for part in (c.brand, c.model) if part)
        lines.append(
            t(
                "bot.admin.carRow",
                lang,
                id=c.id,
                label=label,
                year=c.year,
                odo=c.current_odometer,
                owner=c.user_id,
            )
        )
    body = "\n".join(lines)
    return f"{title}\n\n{body}\n\n{_footer(page, pages, total, lang)}"


def format_stats(stats: dict, lang: str) -> str:
    title = t("bot.admin.statsTitle", lang)
    body = t(
        "bot.admin.statsBody",
        lang,
        users=stats["users"],
        verified=stats["verified_users"],
        telegram=stats["users_with_telegram"],
        cars=stats["cars"],
        logs=stats["log_entries"],
    )
    return f"{title}\n\n{body}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/bot/test_admin_lists.py -v`
Expected: all tests PASS (the 4 from Task 1 plus the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/bot/admin.py backend/tests/bot/test_admin_lists.py
git commit -m "feat(bot): admin-mode state, keyboards, and list formatters"
```

---

## Task 4: Wire the `/admin` command and `adm:` callbacks into the bot

**Files:**
- Modify: `backend/app/bot/handlers.py` (add one command handler and one callback handler; add the `admin` import)
- Modify: `backend/app/bot/main.py` (add the `/admin` menu entry)

**Interfaces:**
- Consumes: `app.bot.admin` (Task 3), `service` admin helpers (Task 1), i18n keys (Task 2), the existing `service.get_user_by_chat`, `normalize_lang`, `SessionLocal`.
- Produces: no new symbols other bots depend on; registers `@router.message(Command("admin"))` and `@router.callback_query(F.data.startswith("adm:"))`.

**Gate rule (applies to both handlers):** resolve the linked `User` via `service.get_user_by_chat`; if it is `None` or `not user.is_superadmin`, reply with `t("bot.admin.notAdmin", lang)` and return. A forged `adm:` callback from a non-admin gets the same rejection via `callback.answer`.

- [ ] **Step 1: Add the import**

In `backend/app/bot/handlers.py`, next to the existing `from app.bot import service` line (line 26), add:

```python
from app.bot import admin as bot_admin
```

- [ ] **Step 2: Add the `/admin` command handler**

Insert after `cmd_backup` (immediately before `_was_asked_for_odometer`, around line 550):

```python
def _admin_lang(user: Optional[User], message: Message) -> str:
    return (
        normalize_lang(user.language)
        if user
        else normalize_lang(getattr(message.from_user, "language_code", None))
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Toggle owner-only admin mode. Gated by is_superadmin, so a non-owner who
    discovers the command sees only the plain rejection."""
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
    lang = _admin_lang(user, message)
    if user is None or not user.is_superadmin:
        await message.answer(t("bot.admin.notAdmin", lang))
        return
    chat_id = message.chat.id
    if bot_admin.is_admin_mode(chat_id):
        bot_admin.set_admin_mode(chat_id, False)
        await message.answer(t("bot.admin.off", lang))
        return
    bot_admin.set_admin_mode(chat_id, True)
    await message.answer(
        t("bot.admin.on", lang) + "\n\n" + t("bot.admin.menuTitle", lang),
        reply_markup=bot_admin.menu_keyboard(lang),
    )
```

- [ ] **Step 3: Add the `adm:` callback handler**

Insert near the other `@router.callback_query` handlers (e.g. after `cb_odometer`, around line 816):

```python
@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(callback: CallbackQuery) -> None:
    """Render an admin page in place. Re-checks is_superadmin every time — the
    callback data is client-supplied, and admin rights can change between the
    keyboard being drawn and a button being tapped."""
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer()
        return
    with SessionLocal() as db:
        user = service.get_user_by_chat(db, str(message.chat.id))
        lang = _admin_lang(user, message)
        if user is None or not user.is_superadmin:
            await callback.answer(t("bot.admin.notAdmin", lang), show_alert=True)
            return
        try:
            _, kind, page_raw = (callback.data or "").split(":")
            page_index = max(0, int(page_raw))
        except ValueError:
            await callback.answer(t("bot.h.badData", lang))
            return

        if kind == "close":
            try:
                await message.edit_text(t("bot.admin.closed", lang))
            except TelegramBadRequest:
                pass
            await callback.answer()
            return

        if kind == "menu":
            try:
                await message.edit_text(
                    t("bot.admin.menuTitle", lang),
                    reply_markup=bot_admin.menu_keyboard(lang),
                )
            except TelegramBadRequest:
                pass
            await callback.answer()
            return

        if kind == "stats":
            text = bot_admin.format_stats(service.admin_stats(db), lang)
            keyboard = bot_admin.menu_keyboard(lang)
        elif kind == "users":
            total = service.admin_count_users(db)
            pages = max(1, (total + bot_admin._ADMIN_PAGE - 1) // bot_admin._ADMIN_PAGE)
            page_index = min(page_index, pages - 1)
            rows = service.admin_list_users(
                db, page_index * bot_admin._ADMIN_PAGE, bot_admin._ADMIN_PAGE
            )
            text = bot_admin.format_users(
                db, rows, page_index + 1, pages, total, lang
            )
            keyboard = bot_admin.page_keyboard("users", page_index + 1, pages, lang)
        elif kind == "cars":
            total = service.admin_count_cars(db)
            pages = max(1, (total + bot_admin._ADMIN_PAGE - 1) // bot_admin._ADMIN_PAGE)
            page_index = min(page_index, pages - 1)
            rows = service.admin_list_cars(
                db, page_index * bot_admin._ADMIN_PAGE, bot_admin._ADMIN_PAGE
            )
            text = bot_admin.format_cars(rows, page_index + 1, pages, total, lang)
            keyboard = bot_admin.page_keyboard("cars", page_index + 1, pages, lang)
        else:
            await callback.answer(t("bot.h.badData", lang))
            return

    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # Telegram rejects an edit to identical text/markup — e.g. tapping the
        # same page twice. Nothing to change; just acknowledge the tap.
        pass
    await callback.answer()
```

- [ ] **Step 4: Add the `/admin` menu entry**

In `backend/app/bot/main.py`, inside `bot_commands` (the list returned around lines 23–30), append after the `backup` entry:

```python
        BotCommand(command="admin", description=t("bot.cmd.admin", lang)),
```

- [ ] **Step 5: Verify the bot module imports cleanly**

Run: `cd backend && python -c "import app.bot.handlers, app.bot.main; print('bot imports OK')"`
Expected: prints `bot imports OK` with no ImportError / NameError.

- [ ] **Step 6: Run the full admin test file once more**

Run: `cd backend && python -m pytest tests/bot/test_admin_lists.py -v`
Expected: all tests PASS (nothing in the handler wiring should have broken the service/formatters).

- [ ] **Step 7: Commit**

```bash
git add backend/app/bot/handlers.py backend/app/bot/main.py
git commit -m "feat(bot): /admin command + paginated user/car/stats views"
```

---

## Task 5: Manual smoke check (local, no deploy)

**Files:** none (verification only).

This project's bot needs a real Telegram token to poll, so the automated tests cover the logic and this step is a human-driven sanity check the implementer runs only if a local bot token is available. It is NOT a deploy.

- [ ] **Step 1: Confirm the owner account is a superadmin locally**

The `/admin` gate needs `User.is_superadmin = True` on the account whose `telegram_chat_id` matches the owner's chat. On the local DB, verify (or set) it:

Run: `cd backend && python -c "from app.database import SessionLocal; from app.models import User; from sqlalchemy import select; db=SessionLocal(); u=db.execute(select(User).where(User.is_superadmin.is_(True))).scalars().all(); print([x.email for x in u])"`
Expected: prints the owner's email in the list. If empty, that's expected on a fresh local DB — the check is informational; do not modify prod data.

- [ ] **Step 2: Report readiness to the user**

Summarize: commands added (`/admin` toggles mode; inline Users/Cars/Stats with ◀/▶ paging 20/page), the gate (`is_superadmin` + rejection string), that sensitive columns are never shown, and that **nothing has been pushed or deployed** — everything is local commits awaiting the user's explicit go-ahead.

---

## Self-Review Notes

- **Spec coverage:** users list ✅ (Task 1/3/4), cars list ✅, "everything useful about users" → per-user car count + verified + provider + join date on the user row, plus a global Stats view ✅. Pagination 20/page ✅ (`_ADMIN_PAGE = 20`, `min(page_index, pages-1)` clamps overruns). Admin/user toggle via `/admin` ✅. Same-account logbook untouched ✅ (all existing handlers unchanged; admin handlers are additive and gated).
- **Type consistency:** `_ADMIN_PAGE` referenced as `bot_admin._ADMIN_PAGE` in the handler matches its definition in `admin.py`. `page_keyboard` takes 1-based `page`; callback data carries 0-based index; the handler converts with `page_index + 1` for display and `page_index * _ADMIN_PAGE` for offset — consistent across Task 3 and Task 4. Formatter signatures (`format_users(db, users, page, pages, total, lang)`, `format_cars(cars, page, pages, total, lang)`, `format_stats(stats, lang)`) match their call sites.
- **Security:** every command + callback re-checks `is_superadmin`; sensitive columns never read in formatters (test asserts `SECRET-HASH`/`SECRET-CODE` absent). Callback data is validated (`split(":")` guarded, `int()` guarded, page clamped ≥ 0 and ≤ pages-1).
- **No placeholders:** all code blocks are complete and copy-ready.
