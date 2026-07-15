# «Дані в безпеці» (решта) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Бекап і Alembic уже зроблені в ітерації «Повний контроль» — тут решта пунктів безпеки даних.

**Goal:** Користувач не може втратити дані (експорт/імпорт) і доступ (скидання пароля через Telegram); брутфорс логіна неможливий; кожен запис має `updated_at` для майбутньої офлайн-синхронізації.

**Tech Stack:** наявний (FastAPI/SQLAlchemy/Alembic; React/zustand; pytest/vitest). Без нових залежностей.

## Global Constraints

- НЕ торкатися `backend/app/services/ocr.py`, `backend/tests/test_ocr.py` (паралельна сесія). `backend/app/config.py` правити ХІРУРГІЧНО — тільки додавати свої рядки, не переставляти чужі (там GEMINI_* і BACKUP_* інших робіт).
- Повний pytest — лише фіналізатор (`--ignore=tests/test_ocr.py`, потім один повний). Імплементаційні агенти — тільки цільові тести.
- Жодних git-команд. UI українською. Ownership 404. Axios лише через спільний клієнт.

---

## Task 1: Міграція 0003 — updated_at + reset-поля

**Files:** Modify `backend/app/models.py`; Create `backend/alembic/versions/0003_updated_at_reset.py`; Test `backend/tests/test_migrations.py` (додати кейс)

**Interfaces:**
- `cars.updated_at`, `log_entries.updated_at`, `service_intervals.updated_at`: `DateTime, nullable=True, default=utcnow, onupdate=utcnow` (SQLAlchemy рівень; існуючі рядки лишаються NULL — це ок).
- `users.reset_code_hash: String(255) NULL`, `users.reset_code_expires_at: DateTime NULL`.
- Схеми відповіді Car/LogEntry/Interval додають `updated_at: datetime | None`.
- Тест: міграція на легасі-базі додає колонки; PATCH запису проставляє updated_at.

## Task 2: Експорт

**Files:** Create `backend/app/routers/export.py`, `backend/app/services/export.py`; Modify `backend/app/main.py`; Test `backend/tests/test_export.py`

**Interfaces:**
- `GET /api/export` → JSON-attachment `kapot-tracker-export-YYYYMMDD.json`:
  `{schema_version: 1, exported_at, cars: [{brand, model, generation, engine, year, fuel_type, current_odometer, intervals: [{title, interval_km, interval_days, last_odometer, last_date}], logs: [{type, odometer, date, total_cost, notes, refuel?, maintenance?, repair?, photos: [{filename, content_type, size}]}]}]}` — БЕЗ внутрішніх id (портативність), фото — тільки метадані (файли не пакуються, обмеження задокументувати в README).
- `GET /api/cars/{car_id}/export.csv` → CSV логів, utf-8-sig (Excel-сумісність), колонки: `date,type,odometer,total_cost,liters,price_per_liter,is_full_tank,gas_station,items,parts_cost,labor_cost,category,part_name,warranty_months,warranty_km,notes`; items — через «; ».
- Тести: JSON містить усі сутності сіда і НЕ містить ключів id/user_id/hashed_password ніде в дереві; CSV рядків = логів+1, utf-8-sig BOM; чужого авто CSV → 404.

## Task 3: Імпорт

**Files:** Modify `backend/app/routers/export.py` (той самий модуль), `backend/app/services/export.py`; Test `backend/tests/test_import.py`

**Interfaces:**
- `POST /api/import` (JSON тіла = формат експорту) → 200 `{cars_created, logs_created, intervals_created}`. Політика v1 — append: усе створюється як нове для поточного користувача, id генеруються заново; `schema_version != 1` → 422; валідація полів — повторним використанням наявних Pydantic create-схем (LogEntryCreate тощо); перший невалідний елемент → 422 з зазначенням шляху (`cars[0].logs[3]: ...`), НІЧОГО не створено (транзакція відкочується).
- Кейси: round-trip експорт→імпорт подвоює кількості; імпорт НЕ рухає current_odometer існуючих авто (створюються нові); беззмістовний JSON → 422 без часткових вставок.

## Task 4: Скидання пароля через Telegram

**Files:** Modify `backend/app/routers/auth.py`, `backend/app/auth.py`, `backend/app/schemas.py`; Create `backend/app/services/reset.py`; Test `backend/tests/test_reset.py`

**Interfaces:**
- `POST /api/auth/reset/request {email}` → ЗАВЖДИ 202 `{detail: "Якщо акаунт існує і привʼязаний Telegram — код надіслано."}` (без енумерації користувачів). Якщо юзер існує І `telegram_chat_id` є: згенерувати 6-цифровий код (`secrets.randbelow`), зберегти bcrypt-хеш + expiry now+10 хв у users, надіслати через aiogram Bot (створюється на запит, `session.close()` у finally; немає токена → тихо пропустити, 202 однаково).
- `POST /api/auth/reset/confirm {email, code, new_password}` → 200 при валідному коді (хеш збігся, не прострочений): новий пароль (bcrypt), очистити reset-поля. Інакше 400 `{detail: "Невірний або прострочений код"}` (однаково для всіх причин). `new_password` min 8 символів (422).
- Старі JWT лишаються чинними до свого expiry — задокументувати в коді.
- Тести: happy path (мок відправки, реальний код перехоплюється з мока); неправильний код 400; прострочений 400 (заморозити час чи вручну виставити expiry в минуле); юзер без Telegram → 202, але нічого не збережено; повторний confirm тим самим кодом → 400 (код очищено).

## Task 5: Rate limiting

**Files:** Create `backend/app/ratelimit.py`; Modify `backend/app/routers/auth.py`; Test `backend/tests/test_ratelimit.py`

**Interfaces:**
- `RateLimiter(limit: int, window_seconds: int)` — in-memory sliding window, ключ передається викликом; метод `check(key, now=None) -> bool` (False = перевищено) і `reset(key)`; injectable clock для тестів; потокобезпечність через `threading.Lock`.
- FastAPI-залежності: `/auth/token` — 5 спроб / 5 хв на (ip, email), успішний логін ресетить лічильник; `/auth/register` — 3 / год на ip; `/auth/reset/request` — 3 / 15 хв на (ip, email); `/auth/reset/confirm` — 5 / 15 хв на (ip, email). Перевищення → 429 `{detail: "Забагато спроб. Спробуйте пізніше."}` + заголовок `Retry-After`.
- IP: `request.client.host` (за nginx — X-Forwarded-For перший елемент, задокументувати в nginx.conf проксі-хедер — він уже проставляється? перевірити і за потреби додати `proxy_set_header X-Forwarded-For`).
- Тести: 6-й логін → 429; успіх ресетить; вікно спливає (мок часу); різні email не діляться лімітом.

## Task 6 (Frontend): експорт/імпорт + «Забули пароль?»

**Files:** Modify `frontend/src/views/Garage.jsx`, `frontend/src/views/Login.jsx`, `frontend/src/api/auth.js`; Create `frontend/src/api/backup.js`, `frontend/src/views/ResetPassword.jsx` (роут `/reset`); Modify `frontend/src/App.jsx`; Test — розширити наявні vitest-утиліти, якщо зʼявляться чисті хелпери

**Interfaces:**
- Garage, нова картка «Дані»: «Експортувати все (JSON)» (blob-download через axios), на картці авто — «CSV журналу»; «Імпортувати з файлу» → file picker → клієнтський JSON.parse → ConfirmDialog «Буде додано: N авто, M записів, K інтервалів» → POST /import → тост + refetch.
- Login: лінк «Забули пароль?» → `/reset`: крок 1 (email → request → повідомлення «перевірте Telegram»), крок 2 (код + новий пароль ×2 → confirm → тост → редірект на /login). 429 → показати detail.
- Все через спільний axios-клієнт; reset-ендпоінти працюють без токена (публічні).

## Task 7: Finalize

- README: розділи «Експорт та імпорт даних», «Відновлення пароля» (потрібен привʼязаний Telegram!), «Захист від перебору» + оновити таблицю API.
- nginx.conf: перевірити/додати `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`.
- Верифікація: `pytest --ignore=tests/test_ocr.py` повний зелений → один повний прогін; `npm run build` + `npm run test`; смоук: register → export → import → counts ×2 → reset-flow з мокнутим ботом → rate limit 429 на 6-му логіні. `git status --short` у звіт, БЕЗ комітів.
