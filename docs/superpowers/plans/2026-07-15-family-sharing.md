# Ітерація 6 «Сімʼя» — Implementation Plan

**Goal:** Одним авто можуть користуватися кілька людей: власник запрошує посиланням, у кожного запису видно автора, права розділені (owner / editor / viewer).

**Чому це епік, а не фіча:** зачіпає КОЖНУ перевірку прав у бекенді. Тому окрема ітерація з окремим ревʼю саме на ownership.

**Архітектурне рішення:** `cars.user_id` **лишається** як денормалізований власник (жодних змін у наявних запитах, де він є). Додається таблиця членства; хелпер доступу враховує обидва джерела. Це найменш інвазивний шлях: наявні 250+ тестів мають лишитися зеленими без правок.

## Global Constraints

- НЕ торкатися `backend/app/services/ocr.py`, `backend/tests/test_ocr.py`. НЕ рестайлити фронтенд. Примітиви: Button, TextField, SelectField, Card, Toggle, Menu, Spinner, ErrorMessage, Modal, ConfirmDialog.
- Жодних git-команд. Alembic-ланцюг лінійний. TDD. Тільки цільові тести (повний прогін — фіналізатор).
- **Правило безпеки №1:** жоден роут не має віддавати чужі дані. Кожен новий/змінений роут — з тестом «інший користувач → 404».

---

## Task 1: Модель членства + міграція з бекфілом

**Files:** `backend/app/models.py`, `backend/alembic/versions/00XX_car_members.py`, `backend/tests/test_members.py`

- `car_members(id, car_id FK cascade, user_id FK cascade, role String(10), created_at, UniqueConstraint(car_id, user_id))`. Ролі: `owner`, `editor`, `viewer`.
- `log_entries.author_id FK users NULL` (NULL = легасі/невідомо).
- `users.display_name String(80) NULL` — для підпису автора.
- **Бекфіл у міграції:** для кожного наявного `cars` рядка створити `car_members(car_id, user_id=cars.user_id, role='owner')`. Ідемпотентно (guard за наявністю рядка). `log_entries.author_id` лишається NULL для історії — НЕ вгадувати автора.
- Тести: міграція на копії реальної dev-бази створює рівно 1 owner-членство на авто, 19 записів цілі; повторний прогін — no-op.

## Task 2: Хелпери доступу (серце ітерації)

**Files:** `backend/app/access.py` (new), `backend/app/routers/cars.py` (get_owned_car → делегує), `backend/tests/test_access.py`

- `ROLE_RANK = {'viewer': 1, 'editor': 2, 'owner': 3}`.
- `get_accessible_car(db, user, car_id, min_role='viewer') -> Car` — 404 якщо авто нема; 404 якщо користувач не власник (`car.user_id == user.id`) і не має членства; **403** якщо доступ є, але рангом нижче за `min_role`. (404 vs 403: «не твоє» ховаємо, «твоє, але прав мало» — чесно кажемо.)
- `user_role_for_car(db, user, car) -> 'owner'|'editor'|'viewer'|None` (власник завжди 'owner', навіть без рядка членства).
- `list_accessible_cars(db, user) -> list[Car]` — власні + через членство, без дублікатів, стабільний порядок (id).
- **Рефактор наявного:** `get_owned_car` перейменувати НЕ треба — зробити його тонкою обгорткою `get_accessible_car(..., min_role='owner')`, а роути, де достатньо нижчих прав, перевести на `get_accessible_car` явно:
  - `viewer+`: GET cars, GET logs/{id}, GET logs list, GET intervals, GET analytics, GET report, GET photos, GET obd, GET documents, GET specs, GET refuel-context, GET export.csv
  - `editor+`: POST/PATCH/DELETE logs, POST/DELETE photos, POST intervals/{id}/complete, POST obd, POST documents
  - `owner`: PATCH/DELETE car, POST/PATCH/DELETE intervals (правила обслуговування — власника), presets, POST/PATCH/DELETE specs, members/invites, GET /api/export (весь акаунт)
- `get_owned_log`/`get_owned_interval`/`get_owned_photo` тощо — переписати через `get_accessible_car` з відповідним min_role, зберігши сигнатури.
- Тести (`test_access.py`): матриця роль×дія (owner/editor/viewer/чужий × read/write/admin) — параметризований тест, кожна клітинка перевірена; чужий завжди 404; viewer на write → 403; editor на PATCH авто → 403.

## Task 3: Інвайти

**Files:** `backend/app/routers/members.py` (new), `backend/app/services/invites.py` (new), міграція, `backend/tests/test_invites.py`

- `car_invites(id, car_id FK cascade, token_hash String(255), role String(10), created_by FK users, expires_at DateTime, used_by FK users NULL, used_at DateTime NULL, created_at)`.
- Токен: `secrets.token_urlsafe(32)`, у базі — **лише bcrypt-хеш** (як reset-коди). TTL 7 днів, одноразовий.
- `POST /api/cars/{car_id}/invites {role: 'editor'|'viewer'}` (owner) → 201 `{token, invite_path: "/join/<token>", expires_at}` — токен віддається **лише раз**.
- `GET /api/invites/{token}` (auth) → `{car: {brand, model, year}, role, inviter_label}` — прев'ю перед прийняттям; невалідний/прострочений/використаний → 404.
- `POST /api/invites/{token}/accept` (auth) → 201 членство; ідемпотентно: якщо вже член — 200 з наявною роллю; **власник не може прийняти інвайт на своє авто** → 400.
- `GET /api/cars/{car_id}/members` (viewer+) → `[{user_id, label, role, is_you, created_at}]`; `label` = `display_name` або частина email до `@`.
- `DELETE /api/members/{member_id}` — owner може видалити будь-кого крім себе; будь-хто може видалити **себе** («вийти з авто»); власника видалити не можна → 400.
- `PATCH /api/members/{member_id} {role}` (owner) — змінити роль; роль owner не призначається через членство → 400.
- Тести: повний життєвий цикл; прострочений токен 404; повторне використання 404; чужий інвайт (не для тебе) — прийняти можна (лінк-based, це задум), але не двічі; viewer не може створити інвайт (403); вихід з авто прибирає доступ (наступний GET → 404).

## Task 4: Авторство записів

**Files:** `backend/app/routers/logs.py`, `backend/app/schemas.py`, `backend/app/bot/service.py`, `backend/tests/test_authorship.py`

- На створенні лога (API і бот) — `author_id = current_user.id`. PATCH автора НЕ змінює.
- `LogEntryOut.author: {id, label} | null`. Eager-load автора (selectinload) у КОЖНОМУ запиті, де вже є refuel/maintenance/repair/expense/photos — інакше N+1.
- `GET /api/auth/me` віддає `display_name`; `PATCH /api/auth/me {display_name}` — оновлення (валідація: 1..80, trim).
- Тести: створений лог має автора; легасі-лог (author_id NULL) серіалізується з `author: null` і не валить PDF/аналітику; query-count guard на списку логів (не росте з кількістю записів).

## Task 5 (Frontend): доступ, інвайти, автор

**Files:** `frontend/src/views/Garage.jsx`, `frontend/src/views/JoinCar.jsx` (new, роут `/join/:token` — **публічний прев'ю, але прийняття вимагає логіна**), `frontend/src/App.jsx`, `frontend/src/api/members.js` (new), `frontend/src/components/LogTimelineItem.jsx`, `frontend/src/views/LogDetail.jsx`, `frontend/src/store/carStore.js`

- Гараж, картка «Спільний доступ» (тільки для owner): список учасників з ролями і бейджем «ви», кнопка «Запросити» → Modal з вибором ролі (Редактор / Спостерігач) → показує лінк з кнопкою копіювання і терміном дії; видалення учасника через ConfirmDialog; для не-власника — рядок «Ви маєте доступ як Редактор» + кнопка «Вийти з авто» (ConfirmDialog).
- `/join/:token`: якщо не залогінений → показати прев'ю авто і кнопки «Увійти» / «Зареєструватися» (після логіна повертає назад на /join/:token через `?next=`); якщо залогінений → «Приєднатися до Volkswagen Golf як Редактор» → accept → тост → редірект у Гараж з новим авто.
- Автор: у рядку журналу і на деталях — маленький чіп з `label` автора, **лише якщо в авто більше одного учасника** (інакше шум).
- Права в UI: viewer не бачить кнопок додавання/редагування/видалення (ховати, не блокувати); editor не бачить редагування авто/інтервалів і картки спільного доступу. Роль брати з нового поля `CarOut.your_role` (додати в Task 2: бекенд віддає роль поточного користувача в кожному CarOut).
- Тести (vitest): чиста функція `canEdit(role, action)` в `src/utils/permissions.js` — матриця ролей; використовується всіма вью.

## Task 6: Бот і сповіщення

**Files:** `backend/app/bot/service.py`, `backend/app/bot/handlers.py`, `backend/tests/test_bot_sharing.py`

- Список авто в боті = `list_accessible_cars` (свої + спільні), у виборі авто спільні позначені «(спільне)».
- Запис через бота — з `author_id`.
- **Нагадування про ТО — лише власнику** (щоб не спамити всіх учасників). Задокументувати в README як свідоме рішення.
- Тести: бот бачить спільне авто; viewer не може створити запис через бота (ввічлива відмова українською).

## Task 7: Finalize

- README: розділ «Спільний доступ» (ролі, інвайт на 7 днів одноразовий, нагадування лише власнику, автор запису), оновити API-таблицю і роадмап.
- Верифікація: повний pytest (`--ignore=tests/test_ocr.py`, потім повний) — **усі наявні тести мають лишитися зеленими без правок** (це головний індикатор, що рефактор прав нічого не зламав); `npm run build` + `npm run test`; міграційний смоук на копії реальної бази; e2e: два користувачі — інвайт → accept → editor бачить авто і створює запис з автором → viewer не може → вихід прибирає доступ.
- **Ревʼю ownership окремим агентом:** пройти по КОЖНОМУ роуту застосунку (grep усіх `@router.`) і перевірити, що min_role відповідає таблиці з Task 2; будь-який роут без перевірки доступу — блокер.
- `git status --short` у звіт. **Без комітів.**
