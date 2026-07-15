# Ітерація 5 «Документи і діагностика» — Implementation Plan

**Goal:** Kapot перестає бути «рахувачкою грошей» і стає медичним журналом авто: OBD-діагностика з Car Scanner, тех-довідник під капот, бібліотека документів, VIN/номер, аналітика АЗС.

**Обґрунтування скоупу:** спайк `docs/research/2026-07-15-vehicle-registry-spike.md` зняв авто-ОСЦПВ (джерела не існує) і підняв VIN+номер до P1/S. OBD-імпорт і тех-довідник — з розділу ідей Gemini (P2, Ітерація 5). Бібліотека документів — з аудиту домену OCR.

## Global Constraints

- НЕ торкатися `backend/app/services/ocr.py`, `backend/tests/test_ocr.py` (паралельна сесія). НЕ рестайлити фронтенд (дизайн-сесія). Примітиви: Button, TextField, SelectField, Card, Toggle, Menu, Spinner, ErrorMessage, Modal, ConfirmDialog.
- Жодних git-команд. Alembic-ланцюг лінійний, продовжувати від останньої ревізії. TDD. Тільки цільові тести.
- Файлові сховища — через спільний сервіс фото (`app/services/photos.py`), не копіпастити збереження на диск.

---

## Task 0: Борг з ітерації 3 (знайдено верифікатором, не виправлено там)

**A. `avg_daily_km` рахує середнє за все життя авто — P1/S.**
`app/services/intervals.py:compute_avg_daily_km` бере перший і останній лог за весь час. Для Гольфа це 66 км/день з 2016 року — але німецький період і український відрізняються в рази, а прогноз дати ТО будується саме на цьому числі.
- Змінити на **вікно останніх 90 днів**: брати логи за `today - 90 днів`, рахувати `(max_odo - min_odo) / days_span`. Якщо в вікні < 2 логів або span < 7 днів — розширювати вікно до 180, потім 365 днів; якщо й там мало — фолбек на середнє за все життя; якщо і це неможливо — 40 (наявний дефолт).
- **Override:** `cars.avg_daily_km_override Float NULL` (міграція разом з іншими цієї ітерації). Якщо задано — використовується замість обчисленого. `CarOut` віддає `avg_daily_km` (ефективне значення), `avg_daily_km_computed` і `avg_daily_km_override`.
- Frontend: у формі авто поле «Середній пробіг, км/день» з плейсхолдером-підказкою «авто: N (за 90 днів)» — порожнє поле = авто-режим.
- Тести: вікно 90 днів працює; розширення вікна при нестачі даних; override має пріоритет; фолбек 40 на порожньому авто; **тест саме на дані Гольфа**: 19 логів 2016→2026, вікно 90 днів має дати число з українського періоду, а не з німецького.

**B. Кнопка «Нагадати через 7 днів» бреше — P1/S.**
`app/bot/service.py:snooze_interval` викликає `stamp_notified(last_notified_at=today)` — байт-у-байт те саме, що робить звичайне нагадування. Тобто кнопка не робить нічого понад стандартний 7-денний кулдаун.
- Додати `service_intervals.snoozed_until Date NULL` (та сама міграція). Кнопка ставить `snoozed_until = today + 7 днів`. Запит нагадувань виключає інтервали зі `snoozed_until >= today`. Виконання інтервалу (`complete`) скидає `snoozed_until = None`.
- Тести: після snooze інтервал не потрапляє в нагадування 7 днів; на 8-й день — потрапляє; complete скидає snooze.

**C. Немає catch-all fallback-хендлера в боті — P2/S.**
Невідоме повідомлення (не число, не витрата, не заправка) не отримує жодної відповіді. Додати останній хендлер з українською підказкою: перелік того, що бот розуміє (число = пробіг; «мийка 300» = витрата; «заправка 45л 2500» = заправка; фото чека; /status, /report, /help).

**D. Фото пишеться на диск до коміту транзакції — P3/S.**
`app/bot/service.py` викликає `save_photo_file()` перед `db.commit()`; якщо коміт падає — файл лишається сиротою. Перенести запис файлу після успішного коміту, або видаляти файл у except. Не критично (БД лишається консистентною), але прибрати.

---

## Task 1: VIN + держномер (P1/S — фундамент для решти)

**Files:** `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/vin.py` (new), `backend/alembic/versions/00XX_car_vin_plate.py`, `backend/tests/test_vin.py`, `frontend/src/views/Garage.jsx` (CarForm)

- `cars.vin String(17) NULL`, `cars.plate String(16) NULL`. Валідація VIN: рівно 17 символів, лише `A-HJ-NPR-Z0-9` (без I, O, Q), регістр нормалізується у верхній; **контрольну цифру НЕ перевіряти** (європейські VIN масово її не мають — саме випадок Golf 7 WVWZZZAUZHP541983). Номер: тримати як ввів користувач, `.strip().upper()`, без формат-валідації (є і європейські, і транзитні).
- `app/services/vin.py` — чистий офлайн-декодер, без мережі:
  - `decode_vin(vin) -> {wmi, manufacturer: str|None, country: str|None, model_year: int|None, valid: bool}`
  - WMI-таблиця (перші 3 символи) мінімум для: WVW/WV1/WV2 (Volkswagen, Німеччина), WAU/WA1 (Audi), WBA/WBS (BMW), WDB/WDD/W1K (Mercedes-Benz), VF1/VF3/VF7 (Renault/Peugeot/Citroën, Франція), TMB (Škoda, Чехія), ZFA (Fiat, Італія), JMB/JHM/JN1 (Японія), KMH/KNA (Корея), Y6D/XTA (СНД), 1-5 префікси (США/Канада/Мексика).
  - Модельний рік з 10-го символу за стандартною таблицею ISO 3779 (A=1980…Y=2000, 1=2001…9=2009, A=2010…Y=2030); неоднозначність 1980/2010 розвʼязувати правилом «якщо рік > поточний+1 → відняти 30».
  - Тести: WVWZZZAUZHP541983 → Volkswagen/Німеччина/2017 (H=2017); невалідні символи → valid=False; порожній → valid=False.
- API: `POST /api/vin/decode {vin}` (auth) → результат декодера. Car create/update приймають vin/plate; CarOut їх віддає.
- Frontend: у формі авто поля «VIN» і «Держномер»; після введення 17 символів — виклик decode і **підказка** «Volkswagen, Німеччина, 2017 — підставити рік?» (кнопка підставляє year; ніколи не перезаписує мовчки).

## Task 2: Тех-довідник авто (Cheat Sheet)

**Files:** `backend/app/models.py`, `backend/app/routers/specs.py` (new), `backend/app/services/spec_presets.py` (new), міграція, `backend/tests/test_specs.py`, `frontend/src/views/Garage.jsx` або новий `frontend/src/views/CarSpecs.jsx` + роут `/garage/:carId/specs`

- Таблиця `car_specs(id, car_id FK cascade, category String(50), name String(120), value String(200), sort_order Int default 0)`. Категорії: «Моменти затяжки», «Рідини та обʼєми», «Допуски», «Інше».
- CRUD: `GET/POST /api/cars/{car_id}/specs`, `PATCH/DELETE /api/specs/{spec_id}` (ownership 404).
- `POST /api/cars/{car_id}/specs/preset?key=golf7_16tdi` — bulk-створення пресету. Пресет `golf7_16tdi` (дані з реального сервісного паспорта власника, вписати ДОСЛІВНО):
  - Моменти затяжки: «Колісні болти» = «120 Нм»; «Пробка масляного піддону» = «30 Нм»
  - Рідини та обʼєми: «Олива двигуна» = «~4.6 л»; «Антифриз» = «G13»
  - Допуски: «Допуск оливи» = «VW 507.00»; «Паливо» = «ДП Євро-5»
  - Інше: «Код двигуна» = «CXXB (EA288)»; «Код КПП» = «RTD (5-ст. механіка)»; «Код фарби» = «LI7F (Urano Gray)»
  - **Важливо:** пресет — це стартові значення, все редаговане. Глобальної бази специфікацій НЕ будуємо (нереально підтримувати).
- Frontend: картка «Тех. довідка» на авто в Гаражі → сторінка зі згрупованими рядками, інлайн-редагування, кнопка «Підставити типові для Golf 7 1.6 TDI» (показувати лише коли специфікацій нема).
- Тести: CRUD + ownership; пресет створює рівно 9 рядків; повторний виклик пресету не дублює (idempotent за (car_id, category, name)).

## Task 3: Бібліотека документів

**Files:** `backend/app/models.py`, `backend/app/routers/documents.py` (new), міграція, `backend/tests/test_documents.py`, frontend: секція в Гаражі

- Таблиця `car_documents(id, car_id FK cascade, kind String(30), title String(150), filename, content_type, size, expires_at Date NULL, created_at)`. Kinds: `tech_passport`, `insurance`, `inspection`, `invoice`, `other`.
- Зберігання файлів — **через `app/services/photos.py`** (той самий каталог `uploads/<user_id>/`), приймати `image/*` **і `application/pdf`**, ліміт 10 МБ.
- `POST /api/cars/{car_id}/documents` (multipart: file, kind, title, expires_at?), `GET /api/cars/{car_id}/documents`, `GET /api/documents/{id}` (стрім), `DELETE /api/documents/{id}`.
- **Звʼязок з інтервалами:** якщо `expires_at` заданий і kind у (insurance, inspection) — створити date-only ServiceInterval «{title} (документ)» з `interval_days = 365`, `last_date = expires_at - 365 днів`, щоб нагадування спрацювало за 14 днів до кінця. Робити це в тій самій транзакції; у відповіді повертати `linked_interval_id`.
- Тести: upload PDF і JPG; чужий 404; ліміт 413; неприйнятний тип 415; insurance з expires_at створює інтервал; видалення документа НЕ видаляє інтервал (він живе далі).

## Task 4: OBD-імпорт (Car Scanner) — кілер-фіча

**Files:** `backend/app/services/obd.py` (new, парсер — чистий), `backend/app/routers/obd.py` (new), `backend/app/models.py`, міграція, `backend/tests/test_obd.py`, `frontend/src/views/Diagnostics.jsx` (new) + роут `/diagnostics`, `frontend/src/api/obd.js`

**Формат:** Car Scanner ELM OBD2 експортує CSV, де перша колонка — час, решта — по колонці на PID; назви колонок різняться між версіями, мовами і профілями (укр/англ/рос). Тому:

- `parse_obd_csv(text) -> {recorded_at: datetime|None, duration_s: float, metrics: [{key, source_column, unit, samples: [(t, value)]}], unmapped_columns: [str]}` — чиста функція:
  - Роздільник визначати автоматично (`,` або `;`), десяткову кому нормалізувати.
  - Час: перша колонка (`Time`/`SECONDS`/`Час`/`timestamp`) — абсолютний ISO або секунди від старту; обидва варіанти підтримати.
  - **Мапінг колонок → канонічні метрики** за нечітким збігом (lowercase, без пробілів/дужок/одиниць), кожна метрика має список патернів-синонімів:
    - `dpf_soot_mass` — «soot mass», «dpf soot», «маса сажі», «сажа» (г)
    - `dpf_distance_since_regen` — «distance since dpf regeneration», «пробіг з останньої регенерації» (км)
    - `injector_correction_1..4` — «injector correction», «корекція форсунки», «cylinder N correction» (mm³/st)
    - `battery_voltage` — «control module voltage», «battery voltage», «напруга» (В)
    - `coolant_temp` — «coolant temperature», «температура ОЖ» (°C)
    - `boost_pressure` — «boost», «тиск наддуву» (кПа/бар)
    - `engine_rpm`, `vehicle_speed`, `intake_temp`, `fuel_rail_pressure` — базові
  - Невідомі колонки НЕ втрачати: повертати в `unmapped_columns` (UI покаже «не розпізнано: N колонок»).
  - Стійкість: порожні клітинки, `NaN`, `-`, локалізовані числа, рядки-коментарі на початку файлу — пропускати без падіння.
  - **Санітарні межі** (значення поза межами відкидати як сміття OBD): soot 0..100 г, напруга 6..18 В, температура -40..150 °C, корекція форсунки -10..10 mm³.
- **Зберігання (компактно, без мільйонів рядків):** таблиці `obd_sessions(id, car_id FK cascade, filename, recorded_at, duration_s, sample_count, created_at)` і `obd_metrics(id, session_id FK cascade, key String(50), unit String(20), min Float, max Float, avg Float, last Float, series JSON)`. `series` — **даунсемпл до ≤200 точок** (рівномірне прорідження, зберігати екстремуми). Сирий CSV не зберігаємо (обмеження задокументувати).
- API: `POST /api/cars/{car_id}/obd` (multipart CSV, ≤20 МБ) → 201 `{session: {...}, metrics: [...], unmapped_columns: [...]}`; `GET /api/cars/{car_id}/obd` (список сесій); `GET /api/obd/{session_id}` (сесія з метриками); `DELETE /api/obd/{session_id}`.
- **Health-висновки** (`app/services/obd.py`, чисті функції, українською) — саме те, заради чого все:
  - `dpf_verdict(soot_last, distance_since_regen)`: soot > 24 г → «🔴 Критично: сажовий фільтр потребує уваги»; > 18 → «🟡 Регенерація скоро»; інакше «🟢 В нормі».
  - `injector_verdict(corrections)`: розкид max-min > 3 mm³ → «🟡 Форсунки розбалансовані»; будь-яка |корекція| > 5 → «🔴 Перевірити форсунку N».
  - `battery_verdict(voltage_min)`: < 9.6 В при старті → «🔴 АКБ просідає»; < 12.2 у спокої → «🟡 Недозаряд».
  - Кожен вердикт повертає `{level: 'ok'|'warn'|'crit', text: str}` і йде у відповідь сесії.
- Frontend `/diagnostics`: дроп-зона CSV → аплоад → картки вердиктів (кольорові) + Recharts-графіки по метриках (line, вісь X — секунди) + список сесій з видаленням; empty state пояснює, як експортувати лог із Car Scanner (Налаштування → Записи → Експорт CSV).
- Тести (`tests/test_obd.py`): синтетичні CSV — англійські заголовки; українські заголовки; `;`-роздільник + десяткова кома; невідомі колонки потрапляють в unmapped; сміттєві значення відкидаються санітарними межами; даунсемпл 5000 точок → ≤200 зі збереженням min/max; вердикти по кожному порогу (ok/warn/crit); ендпоінт 201/415 (не CSV)/413/404 чужого авто.

## Task 5: Аналітика АЗС

**Files:** `backend/app/services/stats.py` (доповнити), `backend/app/routers/analytics.py`, `backend/tests/test_station_stats.py`, `frontend/src/views/Analytics.jsx`

- Analytics-відповідь отримує `stations: [{name, refuels, total_liters, total_cost, avg_price_per_liter, avg_consumption_l_100km | null}]`, відсортовано за total_cost desc. `avg_consumption` — середнє по сегментах full-to-full, що **починаються** на цій АЗС (де вимірювання можливе; інакше null). Обчислювати в один прохід із наявного fuel-движка, без N+1.
- Frontend: у Аналітиці таблиця/список «Мої АЗС» під графіками (лише коли заправок ≥ 2).
- Тести: групування регістронезалежне («okko» і «OKKO» — одна станція, канонічна назва — найчастіше вживана); порожні станції (null/'') → «Без назви»; порядок сортування.

## Task 6: Finalize

- README: розділи «Діагностика OBD», «Тех. довідка», «Документи», «VIN і держномер», оновити API-таблицю і роадмап; чесно вказати обмеження (сирий CSV не зберігається; підтримуються профілі Car Scanner з розпізнаваними колонками; глобальної бази специфікацій нема).
- Верифікація: повний pytest (`--ignore=tests/test_ocr.py`, потім один повний), `npm run build` + `npm run test`, `docker compose config -q`, міграційний смоук на копії реальної dev-бази (19 записів цілі), e2e-смоук: авто з VIN → decode → пресет специфікацій → документ-страховка створює інтервал → OBD CSV дає вердикти → analytics містить stations.
- `git status --short` у звіт. **Без комітів.**
