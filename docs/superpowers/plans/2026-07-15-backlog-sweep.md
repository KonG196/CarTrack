# Ітерація 7 «Зачистка беклогу» — Implementation Plan

**Goal:** Закрити найцінніші P2, що лишилися поза ітераціями 1–6: ГБО (тип пального на заправку), графік цін, запас ходу, бюджет місяця, сезонні шини, тижневий дайджест у боті.

**Принцип відбору:** беремо те, що дешеве і відчутне щодня. Свідомо НЕ беремо: скрейпінг цін АЗС по Україні (агенти розійшлися в оцінці, для одного інстансу — баласт на підтримку), світлу тему (нею займається дизайн-сесія), pull-to-refresh (PWA-жест конфліктує з нативним скролом на iOS).

## Global Constraints

- НЕ торкатися `backend/app/services/ocr.py`, `backend/tests/test_ocr.py`. НЕ рестайлити фронтенд. Примітиви: Button, TextField, SelectField, Card, Toggle, Menu, Spinner, ErrorMessage, Modal, ConfirmDialog.
- Жодних git-команд. Alembic-ланцюг лінійний. TDD. Тільки цільові тести.

---

## Task 1: Тип пального на кожну заправку (ГБО)

**Files:** `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/fuel.py`, `backend/app/services/stats.py`, міграція, `backend/tests/test_dual_fuel.py`, `frontend/src/components/EntryForm.jsx`, `frontend/src/views/Analytics.jsx`

**Чому зараз:** заправок у базі поки нуль — міграція безкоштовна. Пізніше доведеться вгадувати тип для історії.

- `refuel_details.fuel_kind String(10) NULL` — значення: `petrol`, `diesel`, `lpg`, `electric`. NULL = «як у авто» (легасі й одно-паливні авто).
- **Ефективний тип** = `refuel.fuel_kind or car.fuel_type` — обчислюється в одному місці (`app/services/fuel.py:effective_fuel_kind(refuel, car)`), використовується скрізь.
- **Розхід рахується окремо по кожному типу пального.** `compute_fuel_stats` отримує параметр `fuel_kind: str | None`; коли заданий — сегменти full-to-full будуються **лише** з заправок цього типу (інші ігноруються, але їхній пробіг лишається в дистанції — це фізично правильно для ГБО: на бензині ти теж їдеш).
  - **Важливо і неочевидно:** для ГБО-авто «повний бак» бензину і «повний бак» газу — незалежні цикли. Тому сегмент газу = від повного газового до наступного повного газового; проміжні бензинові заправки не рвуть сегмент.
- Analytics: `fuel.by_kind: {kind: {avg_consumption_l_100km, last_consumption_l_100km, avg_cost_per_km, total_liters, total_cost}}`. Наявні поля `fuel.*` лишаються — це агрегат по основному типу авто (щоб не зламати наявні тести і UI).
- UI: у формі заправки селектор типу зʼявляється **лише якщо** `car.fuel_type == 'lpg'` або в авто вже є заправки різних типів (інакше — зайвий шум для 95% користувачів). Аналітика: якщо `by_kind` має >1 ключа — окремі лінії на графіку розходу з легендою.
- Тести: ГБО-авто з чергуванням газ/бензин дає два незалежні середні; одно-паливне авто поводиться точно як раніше (регресія наявних тестів розходу); NULL fuel_kind успадковує тип авто.

## Task 2: Графік цін на пальне

**Files:** `backend/app/services/stats.py`, `backend/app/schemas.py`, `backend/tests/test_price_trend.py`, `frontend/src/views/Analytics.jsx`

- Analytics отримує `price_history: [{date, price_per_liter, fuel_kind, gas_station}]` — усі заправки в хронологічному порядку (обмеження: останні 100).
- UI: line chart «Ціна за літр» у Аналітиці; точки різних типів пального — різні лінії; підказка показує АЗС і дату. Показувати лише коли заправок ≥ 3.
- Тести: порядок за датою; ліміт 100; порожньо → `[]`.

## Task 3: Обʼєм бака і запас ходу

**Files:** `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/fuel.py`, міграція, `backend/tests/test_range.py`, `frontend/src/views/Dashboard.jsx`, `frontend/src/views/Garage.jsx`

- `cars.tank_liters Float NULL` (поле у формі авто; для Golf 7 Variant — 50 л, але **не хардкодити**, лише плейсхолдер-підказка «напр. 50»).
- Analytics/Dashboard: якщо задано `tank_liters` і є `avg_consumption_l_100km` → `range_km = tank_liters / avg_consumption * 100` (округлити до 10 км). Показати на дашборді картку «Запас ходу на повному баку: ~N км».
- **Чесність:** це оцінка на повному баку, а не залишок пального — ми не знаємо поточного рівня. Підпис саме такий, жодних «залишилось N км».
- Тести: без tank_liters → null; без розходу → null; математика.

## Task 4: Бюджет місяця

**Files:** `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/routers/analytics.py`, міграція, `backend/tests/test_budget.py`, `frontend/src/views/Dashboard.jsx`, `frontend/src/views/Garage.jsx`

- `cars.monthly_budget Numeric(10,2) NULL`.
- Analytics отримує `budget: {limit, spent_this_month, projected_month_total, pct_used, status}` (`status`: `ok` < 80%, `warn` 80–100%, `over` > 100% від limit; за відсутності limit → `null`). `projected_month_total` уже існує у forecast — **перевикористати, не рахувати вдруге**.
- UI: на дашборді прогрес-бар «Бюджет місяця: 2 400 / 5 000 ₴» з кольором за статусом; прогноз показувати пунктиром/підписом «прогноз: N ₴». Ховати картку, якщо бюджет не заданий.
- Тести: пороги статусів; без ліміту → null; прогноз береться з forecast.

## Task 5: Сезонні шини

**Files:** `backend/app/models.py`, `backend/app/routers/tires.py` (new), міграція, `backend/tests/test_tires.py`, `frontend/src/views/Garage.jsx`

- Таблиця `tire_sets(id, car_id FK cascade, name String(80), season String(10), size String(30) NULL, dot_year Int NULL, purchased_at Date NULL, odometer_at_install Int NULL, is_installed Bool default False, created_at)`. `season`: `summer`, `winter`, `all_season`.
- `GET/POST /api/cars/{car_id}/tires`, `PATCH/DELETE /api/tires/{id}`, `POST /api/tires/{id}/install` — встановлює цей комплект і **знімає** попередній (в одній транзакції), пише `odometer_at_install = car.current_odometer`.
- Пробіг комплекту = `car.current_odometer - odometer_at_install` (для встановленого) — віддавати як `km_on_set`.
- UI: секція «Шини» в Гаражі: список комплектів з бейджем «встановлені», кнопка «Встановити», форма додавання. Без нагадувань про сезон (дати переобування — вручну через date-інтервал, якщо треба).
- Тести: установка знімає попередній комплект; km_on_set рахується; ownership 404.

## Task 6: Тижневий дайджест у боті

**Files:** `backend/app/bot/reminders.py`, `backend/app/bot/service.py`, `backend/tests/test_digest.py`

- Раз на тиждень (неділя, у тому ж добовому циклі, що й нагадування) — одне повідомлення власнику по кожному авто:
  «📊 Тиждень з Kapot: витрачено N ₴ (заправки M ₴, ТО K ₴); пробіг +X км; середній розхід Y л/100км; найближче ТО: «Олива» через Z км».
  Якщо за тиждень **жодних записів** — дайджест НЕ надсилати (не спамити).
- Прапорець `users.digest_enabled Bool default True` + команда `/digest on|off` у боті.
- Тести: дайджест формується з тижневих даних; порожній тиждень → None; вимкнений прапорець → None; текст містить усі блоки.

## Task 7: Finalize

- README: розділи про ГБО, графік цін, запас ходу, бюджет, шини, дайджест; оновити API-таблицю і роадмап.
- Верифікація: повний pytest (`--ignore=tests/test_ocr.py`, потім повний), `npm run build` + `npm run test`, міграційний смоук на копії реальної бази, `docker compose config -q`.
- **Регресія понад усе:** наявні тести розходу і аналітики мають лишитися зеленими без правок — Task 1 найризикованіший.
- `git status --short` у звіт. **Без комітів.**
