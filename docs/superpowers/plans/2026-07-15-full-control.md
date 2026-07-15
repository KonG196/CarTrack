# «Повний контроль» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перегляд і редагування всього (записи, інтервали, пробіг) + фото до записів + пошук + дублювання + Alembic-міграції + щоденний бекап у Telegram.

**Architecture:** Бекенд додає таблицю `log_photos` з файловим сховищем на диску, параметр пошуку `q`, Alembic поверх наявної схеми та модуль бекапу. Фронтенд отримує детальну сторінку `/logbook/:id`, спільну `EntryForm` для створення/редагування/дублювання і примітиви `Modal`/`ConfirmDialog`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic; React 18 (JSX) + zustand + axios; pytest + vitest.

## Global Constraints

- **НЕ торкатися** `backend/app/services/ocr.py` і `backend/tests/test_ocr.py` — їх редагує паралельна сесія. Не запускати повний pytest до фінальної верифікації; фінальний прогін — `pytest --ignore=tests/test_ocr.py`, потім один повний з приміткою.
- **Жодних git-комітів** — користувач керує історією сам.
- UI-тексти українською; стиль — наявна темна slate-тема, примітиви з `components/UI/`.
- Всі нові ендпоінти: ownership через `get_owned_*` (404 для чужих ресурсів), помилки `{detail}`.
- Всі HTTP-виклики фронтенда — через спільний axios-клієнт `src/api/client.js` (Bearer-інтерцептор).
- Backend-тести: стиль наявного `tests/conftest.py` (TestClient + тимчасова SQLite, override get_db).

---

## Track A — Backend

### Task 1: Alembic поверх наявної схеми

**Files:**
- Modify: `backend/requirements.txt` (+`alembic`)
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_baseline.py`
- Modify: `backend/app/migrations.py` (додати `run_migrations`), `backend/app/main.py` (lifespan), `backend/app/bot/main.py` (стартова міграція)
- Test: `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: `app.migrations.run_migrations(engine) -> None` — викликається в lifespan API і на старті бота ЗАМІСТЬ прямого `create_all`; `ensure_schema` лишається і викликається всередині `run_migrations` після upgrade (фолбек для старих dev-баз).

**Логіка `run_migrations`:**
1. Якщо немає таблиці `alembic_version`: якщо є таблиця `users` (стара база) → `alembic stamp 0001_baseline`; якщо база порожня → нічого.
2. `alembic upgrade head` (програмно: `alembic.command.upgrade(cfg, "head")`, `sqlalchemy.url` — з `settings.DATABASE_URL`).
3. `ensure_schema(engine)`.

`0001_baseline` створює ВСІ поточні таблиці (users, cars, log_entries, refuel_details, maintenance_details, repair_details, service_intervals) — згенерувати autogenerate'ом на порожній базі й перевірити руками, що типи збігаються з models.py.

- [ ] **Step 1:** Тести: (а) порожня SQLite → `run_migrations` → усі 7 таблиць + `alembic_version`; (б) «стара» база (створена `Base.metadata.create_all`) → `run_migrations` → stamped і не падає; (в) повторний виклик — no-op.
- [ ] **Step 2:** Прогнати — FAIL (немає run_migrations).
- [ ] **Step 3:** Реалізувати (alembic init, env.py з `target_metadata = Base.metadata`, baseline, run_migrations).
- [ ] **Step 4:** `pytest tests/test_migrations.py -q` → PASS. Також `pytest tests/test_auth.py -q` (стара поведінка не зламана).

### Task 2: Фото записів

**Files:**
- Modify: `backend/app/models.py` (+`LogPhoto`), `backend/app/schemas.py` (+`PhotoOut`, `LogEntryOut.photos`), `backend/app/config.py` (+`UPLOADS_DIR: str = "./uploads"`), `backend/app/main.py` (router)
- Create: `backend/app/routers/photos.py`, `backend/alembic/versions/0002_log_photos.py`
- Modify: `backend/app/routers/logs.py` (selectinload photos у списку — без N+1!)
- Test: `backend/tests/test_photos.py`

**Interfaces:**
- Produces: `LogPhoto(id, log_entry_id FK cascade, filename, content_type, size, created_at)`; файл на диску `<UPLOADS_DIR>/<user_id>/<uuid4>.<ext>`.
- `POST /api/logs/{log_id}/photos` multipart `file` (image/*, ≤10 МБ) → 201 `PhotoOut{id, filename, content_type, size, created_at}`; 415/413/404.
- `GET /api/photos/{photo_id}` → файл (FileResponse, правильний content-type); 404 для чужого.
- `DELETE /api/photos/{photo_id}` → 204; видаляє рядок і файл (відсутність файлу не валить запит).
- `LogEntryOut` отримує `photos: list[PhotoOut]` (скрізь, включно зі списком).

- [ ] **Step 1:** Тести: upload → 201 і файл існує на диску; список логів містить `photos`; чужий користувач → 404 на всіх трьох; text/plain → 415; >10МБ → 413; DELETE → 204 і файл зник; видалення ЛОГА каскадно видаляє фото-рядки.
- [ ] **Step 2:** FAIL → **Step 3:** реалізація (міграція 0002 autogenerate) → **Step 4:** `pytest tests/test_photos.py tests/test_logs.py -q` → PASS.

### Task 3: Пошук + одиничний GET лога

**Files:**
- Modify: `backend/app/routers/logs.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- `GET /api/cars/{car_id}/logs?q=<str>` — фільтр (OR, case-insensitive `ilike`): `LogEntry.notes`, `MaintenanceDetails.items` (cast → String), `RepairDetails.category`, `RepairDetails.part_name`, `RefuelDetails.gas_station`. Outer joins, `distinct()`. Комбінується з `type`, `limit`, `offset`; `total` — з урахуванням фільтра. Примітка в коді: SQLite не кейс-фолдить кирилицю в LIKE — на проді (Postgres) ilike повноцінний.
- `GET /api/logs/{log_id}` → `LogEntryOut` (ownership 404) — потрібен LogDetail-сторінці.

- [ ] **Step 1:** Тести: пошук по нотатках; по items ТО («Фільтр» знаходить запис); по category ремонту; по gas_station; q + type разом; q без збігів → items=[], total=0; латиниця різного регістру матчиться; GET одиничного лога свій/чужий.
- [ ] **Step 2:** FAIL → **Step 3:** реалізація → **Step 4:** `pytest tests/test_search.py tests/test_logs.py -q` → PASS.

### Task 4: Бекап

**Files:**
- Create: `backend/app/backup.py` (CLI-запуск: `python -m app.backup` через блок `if __name__ == "__main__"`)
- Modify: `backend/app/config.py` (+`BACKUP_DIR: str = "./backups"`, `BACKUP_KEEP: int = 14`, `BACKUP_TELEGRAM_CHAT_ID: str = ""`), `backend/app/bot/reminders.py` (щоденний виклик після нагадувань)
- Test: `backend/tests/test_backup.py`

**Interfaces:**
- `create_backup(dest_dir: Path | None = None) -> Path` — SQLite: гарячий бекап через `sqlite3.Connection.backup()` (НЕ копіювання файлу — база під запущеним uvicorn); Postgres: `pg_dump` → `.sql.gz`. Імʼя: `kapot_tracker-YYYYMMDD-HHMMSS.db`.
- `rotate_backups(dest_dir: Path, keep: int = 14) -> int` — лишає найновіші, повертає кількість видалених.
- `send_backup_via_telegram(path: Path) -> bool` — aiogram `Bot.send_document` у `BACKUP_TELEGRAM_CHAT_ID`; порожній chat_id → False без помилки. **Не** розсилати юзерам: у hosted-режимі бекап містить дані ВСІХ, тому тільки адмінський чат.
- У циклі бота: раз на добу `create_backup()` + `rotate_backups()` + `send_backup_via_telegram()` у try/except.
- `BACKUP_DIR` і `uploads/` — у `.gitignore`.

- [ ] **Step 1:** Тести: create_backup на dev-SQLite → файл починається з магії `SQLite format 3` і містить таблицю users (відкрити копію sqlite3-ом); rotate лишає рівно keep найновіших; send з порожнім chat_id → False (без мережі); телеграм — тільки мок.
- [ ] **Step 2:** FAIL → **Step 3:** реалізація → **Step 4:** `pytest tests/test_backup.py -q` → PASS.

---

## Track B — Frontend

### Task 5: Modal + ConfirmDialog

**Files:**
- Create: `frontend/src/components/UI/Modal.jsx`, `frontend/src/components/UI/ConfirmDialog.jsx`; експорт з `frontend/src/components/UI/index.js`
- Modify: `frontend/src/views/Logbook.jsx`, `frontend/src/views/Garage.jsx` (усі `window.confirm` → ConfirmDialog)

**Interfaces:**
- `Modal({open, onClose, title, children, footer})` — fixed overlay bg-black/60, картка bg-slate-900 border-slate-800 rounded-2xl, Esc і клік по фону закривають.
- `ConfirmDialog({open, title, message, confirmLabel="Видалити", danger=true, onConfirm, onCancel})` — на базі Modal; danger → червона кнопка.

- [ ] Реалізувати → замінити всі window.confirm → `npm run build` зелений; поведінка видалень збережена.

### Task 6: EntryForm + дублювання

**Files:**
- Create: `frontend/src/components/EntryForm.jsx`, `frontend/src/utils/entryForm.js`
- Modify: `frontend/src/views/AddEntry.jsx` (стає обгорткою: створення + `?from=`)
- Test: `frontend/src/utils/entryForm.test.js`

**Interfaces:**
- `entryToFormValues(log) -> values` (utils, чиста) — мапить LogEntry API-обʼєкт у стан форми (для edit і duplicate); `formValuesToPayload(type, values) -> payload` — зворотна (виноситься з поточного handleSubmit без зміни поведінки).
- `EntryForm({mode: 'create'|'edit', type, lockedType=false, initialValues, submitting, onSubmit, scannedFile, onScanFile})` — вся type-специфічна розмітка й валідація переїздить сюди з AddEntry БЕЗ змін поведінки (авто-математика заправки, чекліст ТО, OCR-блок лише для refuel).
- AddEntry: `?from=<id>` → бере запис (зі стора або `GET /logs/{id}`), `entryToFormValues`, дата = сьогодні, пробіг = `car.current_odometer`, фото не тягнуться.

- [ ] **Step 1:** vitest на `entryToFormValues` (по одному кейсу на 4 типи, включно з items/гарантією) і `formValuesToPayload` (симетрія). FAIL → реалізація → PASS.
- [ ] **Step 2:** `npm run build` + ручна перевірка: створення всіх 4 типів працює як раніше.

### Task 7: LogDetail `/logbook/:id`

**Files:**
- Create: `frontend/src/views/LogDetail.jsx`, `frontend/src/api/photos.js`
- Modify: `frontend/src/App.jsx` (route), `frontend/src/components/LogTimelineItem.jsx` (клік → navigate), `frontend/src/api/logs.js` (+`getLog(id)`), `frontend/src/store/carStore.js` (+`editLog`, оновлення списку після PATCH)
- Test: додати кейс у `entryForm.test.js` на edit-prefill

**Interfaces:**
- `photos.js`: `uploadPhoto(logId, file)`, `getPhotoBlob(photoId) -> Blob` (axios responseType blob; `<img>` НЕ може слати Bearer — рендер тільки через object URL з revoke), `deletePhoto(photoId)`.
- LogDetail: перегляд (усі поля за типом: повний items-список і розбивка parts/labor; category/part/гарантія; літри/ціна/бак/АЗС; повні нотатки; фото-галерея з лайтбоксом-Modal і кнопкою «Додати фото») + дії **Редагувати** (інлайн EntryForm mode=edit, lockedType, submit → `PATCH /logs/{id}` → перегляд + тост), **Повторити** (`/add?from=<id>`), **Видалити** (ConfirmDialog → назад у журнал).
- OCR-бонус в AddEntry: після успішного create, якщо був відсканований файл і type=refuel → `uploadPhoto` (помилка тут не валить створення — тост «фото не додалось»).

- [ ] Реалізація → `npm run build` + `npm run test` зелені.

### Task 8: Редагування інтервалів + швидкий пробіг

**Files:**
- Modify: `frontend/src/views/Garage.jsx` (олівець на рядку інтервалу → `IntervalForm initial={interval}` → `updateInterval`), `frontend/src/views/Dashboard.jsx` (олівець біля одометра → інлайн numeric input → `editCar`), `frontend/src/store/carStore.js` (+`editInterval`)

**Interfaces:**
- Consumes: наявні `api/intervals.js updateInterval` і `api/cars.js updateCar` (обидва вже написані, не підключені).
- Введений пробіг < поточного → ConfirmDialog «Нове значення менше за поточне (N км). Точно зменшити?».

- [ ] Реалізація → build зелений; PATCH-и ходять; після зміни пробігу інтервали на дашборді перераховуються (refetch).

### Task 9: Пошук у журналі

**Files:**
- Modify: `frontend/src/views/Logbook.jsx`, `frontend/src/store/carStore.js` (`fetchLogs(carId, {type, q})`), `frontend/src/api/logs.js` (q параметр)

**Interfaces:**
- Поле з іконкою Search над чіпсами, debounce 300 мс (локальний setTimeout-ефект), очищення хрестиком; підпис «Знайдено N з M» при активному q; порожній результат — дружній empty state.

- [ ] Реалізація → build + vitest зелені.

---

## Track C — Фінал

### Task 10: Інфраструктура, README, наскрізна верифікація

**Files:**
- Modify: `.gitignore` (+`backend/uploads/`, `backend/backups/`), `.env.example` (+UPLOADS_DIR, BACKUP_DIR, BACKUP_KEEP, BACKUP_TELEGRAM_CHAT_ID з коментарями), `docker-compose.yml` (volume `uploads`, env бекапу; entrypoint бекенда виконує міграції на старті), `README.md` (розділи «Міграції (Alembic)», «Бекапи», оновити фічі)

**Верифікація:**
- [ ] `pytest --ignore=tests/test_ocr.py -q` → все зелене.
- [ ] Один повний прогін `pytest -q` — якщо падає ТІЛЬКИ test_ocr (паралельна сесія) → зафіксувати в звіті, не чіпати.
- [ ] `npm run build` + `npm run test` → зелені.
- [ ] Наскрізний смоук TestClient-скриптом: register → car → create maintenance з фото (мокнутий файл) → GET /logs/{id} має photos → PATCH запису → пошук знаходить за нотаткою → бекап створюється.
- [ ] `docker compose config -q`.
- [ ] **Без комітів** — показати `git status` у звіті.
