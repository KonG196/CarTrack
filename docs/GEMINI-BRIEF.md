# Kapot Tracker — повний бізнесовий і технічний опис

> **Як читати цей документ.** Це повний знімок продукту станом на **14.07.2026**, підготовлений для AI-співрозмовника, який не має доступу до коду й контексту розробки. Тут є все необхідне, щоб міркувати про продуктові та технічні покращення: бізнес-модель, архітектура з формулами алгоритмів, повний довідник API, схема даних, карта екранів і чесний список обмежень. Технічні ідентифікатори лишаються англійською.

**Зміст**
1. [Продукт і бізнес](#1-продукт-і-бізнес)
2. [Архітектура і алгоритми](#2-архітектура-і-алгоритми)
3. [Довідник API і схема даних](#3-довідник-api-і-схема-даних)
4. [Фронтенд і UX](#4-фронтенд-і-ux)
5. [Інфраструктура, якість, відомі обмеження](#5-інфраструктура-якість-відомі-обмеження)
6. [Куди продукт рухається](#6-куди-продукт-рухається)

---

## 1. Продукт і бізнес

**Kapot Tracker** (робоча назва до 2026-07-14 — CarKeeper; перейменовано сьогодні) — україномовний персональний бортовий журнал автомобіля та трекер витрат: мобільний веб-застосунок (React PWA) + FastAPI-бекенд + Telegram-бот, усе в одному docker-compose-монорепозиторії.

## 1.1. Ідея і ціннісна пропозиція

Ідея народилася як пет-проєкт «на стику автоматизації фінансів, трекінгу та автомобільної тематики»: замість блокнота чи Excel-таблиць — красива і швидка мобільна веб-утиліта, яку власник авто робить насамперед для себе. Ціннісна пропозиція (дослівно з оригінального продуктового плану) стоїть на трьох китах:

1. **«Нуль рутини».** Замість ручного введення кожного літра пального користувач фотографує чек АЗС — застосунок сам витягує суму, об'єм пального та дату (OCR, ендпоінт `POST /api/ocr/scan`, Tesseract ukr+eng), лишається дописати пробіг і підтвердити.
2. **Контроль «здоров'я» авто.** Сервісні інтервали (олива, фільтри, ГРМ, страховка) з нагадуваннями прямо в Telegram — «через 500 км час міняти мастило» — пропустити ТО неможливо. Система рахує залишок ресурсу кожного інтервалу і прогнозує дату наступного обслуговування на основі середньоденного пробігу.
3. **Передпродажна історія («плюс до карми авто»).** В один клік генерується PDF-звіт з усією історією обслуговування (`GET /api/cars/{car_id}/report`) — це суттєво підвищує довіру покупця при продажі машини. Особливо цінно для ринку України, де багато вживаних авто, імпортованих з Європи, без документованої історії.

Додаткова математична «фішка»: точний розрахунок реального розходу пального методом «від повного до повного» (full-to-full): `розхід (л/100 км) = залиті літри / пройдена відстань × 100`, з накопиченням часткових заправок між двома «повними баками».

## 1.2. Цільова аудиторія і юзкейси

**Цільова аудиторія:** приватні власники авто, які хочуть контролювати витрати та технічний стан машини без рутини; у першу чергу — власники вживаних авто (зокрема свіжопригнаних з ЄС), для яких ведення власної сервісної історії — це і спокій, і гроші при перепродажі. Premium-сегмент за задумом — сім'ї та «мікро-автопарки» з кількома авто. Персона №1 — сам автор продукту: власник VW Golf 7 Variant 1.6 TDI 2016 р. (дизель, ~240 тис. км, пригнаний з Німеччини у 2022 р.).

**Ключові юзкейси** (з оригінальної специфікації; журнал має 4–5 типів записів: заправка / ТО / ремонт / регулярні та інші витрати):

- **UC1 — Заправка (3 секунди на АЗС):** одометр + літри/ціна за літр або сума (третє поле вираховується), прапорець «до повного» для розрахунку розходу, опційно назва АЗС.
- **UC2 — Планове ТО і Interval Engine:** користувач один раз задає шаблони («олива: кожні 10 000 км або 365 днів — що настане раніше»); кожен новий запис пробігу оновлює статуси всіх інтервалів («Ресурс оливи: 70%, лишилось 7 000 км або 9 місяців»).
- **UC3 — Позаплановий ремонт:** вузол авто (підвіска/гальма/двигун/електрика…), деталь і бренд, гарантія від СТО; якщо той самий вузол ламається повторно у гарантійний період — застосунок це підсвічує (логіка гарантій — у специфікації, поки що концепт).
- **UC4 — Регулярні витрати з дедлайнами:** страховка/податок з нагадуваннями за 14/7/1 день до закінчення (у специфікації).
- **Telegram як швидкий інтерфейс:** оновлення пробігу простим числом у відповідь боту, «екстрений лог» одним повідомленням (`мийка 300` → запис «інші витрати»), команда `/status`, нагадування про наближення ТО — усе це реалізовано.

## 1.3. Запланована бізнес-модель (ПЛАН, не реалізовано)

Оригінальний план — класична **Freemium-модель**, обґрунтована тим, що OCR і сервери коштують грошей («чистий альтруїзм не спрацює»):

| Фіча | Free | Premium (~$2.99/міс) |
|---|---|---|
| Кількість авто | 1 автомобіль | Безліміт (сім'ї, мікро-автопарки) |
| Введення даних | Тільки ручне | Автосканування чеків (OCR) |
| Сповіщення | Внутрішні пуші у вебі | Telegram-бот (активні нагадування) |
| Аналітика | Базові графіки витрат | Просунута (вартість 1 км, прогноз зносу деталей) |
| Експорт | Немає | Брендований PDF-паспорт обслуговування |

**Додаткові B2B-канали (план):**
- **Партнерська програма з магазинами автозапчастин:** коли підходить час заміни ГРМ/оливи, застосунок пропонує «купити комплект для вашого Golf 7 1.6 TDI на Exist/Autodoc» і отримує реферальний відсоток.
- **Інтеграція з локальними СТО:** запис на партнерське СТО в один клік, коли настає термін ТО.

**Статус реалізації — важливо:** білінгу, підписок, тарифних обмежень і партнерських інтеграцій у коді **немає взагалі**. Зараз усі функції безкоштовні й доступні кожному зареєстрованому користувачу — включно з тими, що за планом мали бути Premium (OCR, Telegram-бот, прогнозна аналітика, PDF-звіт). Тобто продукт де-факто випереджає монетизаційний план по фічах, але сама монетизація — суто на папері. Гараж уже підтримує кілька авто на користувача без ліміту.

## 1.4. Конкурентний контекст

Ніша — клас застосунків Drivvo / Fuelio / Fuelly (мобільні трекери заправок, витрат і ТО). За оцінкою з оригінального плану, ця ніша «або застрягла в дизайні 2012 року, або перевантажена рекламою». Диференціація Kapot Tracker: повністю україномовний продукт, «Telegram-first»-взаємодія (в Україні Telegram — де-факто основний месенджер), OCR саме українських чеків АЗС (ОККО, WOG тощо), дистрибуція як PWA без App Store/Google Play, і PDF-звіт як «передпродажний паспорт» — фіча, заточена під український ринок вживаних авто з ЄС. Формальний конкурентний аналіз (порівняння фіч/цін) не проводився.

## 1.5. Поточний стан (2026-07-14)

- **Один реальний користувач** — автор/власник продукту, продукт у щоденному використанні («dogfooding»). У dev-базі засіяна його **повна реальна сервісна історія**: Volkswagen Golf VII Variant 2016, двигун 1.6 TDI CXXB (EA288), дизель, поточний одометр 240 054 км; **19 записів журналу**, **7 сервісних інтервалів**, задокументовані витрати **87 323 грн** (точно 87 323.28).
- **Етапи 1–3 дорожньої карти виконані:** Етап 1 (MVP: авторизація JWT, гараж, журнал 4 типів записів, розхід full-to-full, інтервали, дашборд і аналітика з графіками, PWA) ✅; Етап 2 (OCR чеків + Telegram-бот) ✅; Етап 3 (PDF-звіт + прогнозна аналітика: середні витрати/міс, прогноз поточного місяця, найближчі ТО з орієнтовною вартістю) ✅.
- **Наступна ітерація «повне редагування» — спроєктована, але не реалізована:** сторінка деталей запису `/logbook/:id` з редагуванням, редагування інтервалів, фотододатки до записів, пошук по журналу, швидкий віджет одометра, дублювання запису.
- **Етап 4 (ідеї з README, не реалізовано):** офлайн-режим PWA (черга синхронізації на IndexedDB), збереження фото чеків у S3/MinIO, мультивалютність.
- **Немає:** білінгу та будь-якої монетизації, B2B-інтеграцій, публічного деплою для сторонніх користувачів, маркетингу. Продукт на стадії «working product for user #1», а не «бізнес».

---

## 2. Архітектура і алгоритми

## 2.1 Загальна схема системи

Kapot Tracker — монорепозиторій з трьох виконуваних компонентів: React PWA (frontend), FastAPI API (backend) та Telegram-бот (окремий процес на тому самому Python-образі). OCR виконується **всередині backend-процесу** (бінарник `tesseract` встановлюється у Dockerfile backend разом з мовними пакетами `tesseract-ocr-ukr` та `tesseract-ocr-eng`).

**Продакшн-режим (docker-compose):**

```
                 ┌─────────────────────────────────────────────┐
                 │  Браузер / встановлена PWA                  │
                 └───────────────┬─────────────────────────────┘
                                 │ HTTP :3000
                 ┌───────────────▼─────────────────────────────┐
                 │  frontend: nginx:alpine (порт 80 у контейн.)│
                 │  - статика PWA (Vite build, SPA-fallback)   │
                 │  - client_max_body_size 12m (для OCR-фото)  │
                 │  - proxy: location /api/ → backend:8000     │
                 └───────────────┬─────────────────────────────┘
                                 │ HTTP (префікс /api зберігається)
                 ┌───────────────▼─────────────────────────────┐
                 │  backend: uvicorn + FastAPI (python:3.12)   │
                 │  - роутери: auth, cars, logs, intervals,    │
                 │    analytics, reports, ocr, telegram        │
                 │  - OCR: pytesseract → tesseract (у цьому    │
                 │    самому контейнері)                       │
                 │  - PDF: reportlab (шрифти DejaVu в образі)  │
                 └───────────────┬─────────────────────────────┘
                                 │ SQLAlchemy (psycopg2)
                 ┌───────────────▼─────────────────────────────┐
                 │  db: postgres:16-alpine (volume pgdata,     │
                 │  healthcheck pg_isready)                    │
                 └───────────────▲─────────────────────────────┘
                                 │ SQLAlchemy (НЕ через HTTP API!)
                 ┌───────────────┴─────────────────────────────┐
                 │  bot: python -m app.bot.main (aiogram v3,   │
                 │  long polling до api.telegram.org;          │
                 │  фоновий reminder_loop кожні 24 год)        │
                 │  compose-профіль "bot":                     │
                 │  docker compose --profile bot up            │
                 └─────────────────────────────────────────────┘
```

**Dev-режим (`scripts/dev.sh`):** Vite dev-сервер на `:5173` проксіює `/api` → uvicorn на `:8000`; БД — файл SQLite `backend/kapot_tracker.db` (`DATABASE_URL=sqlite:///./kapot_tracker.db`, для SQLite додається `connect_args={"check_same_thread": False}`). У docker-compose `DATABASE_URL` перевизначається на `postgresql+psycopg2://...@db:5432/...`. Отже одна кодова база працює і на SQLite (dev), і на PostgreSQL (prod).

Ключовий архітектурний факт: **бот не ходить у HTTP API** — він імпортує ті самі ORM-моделі та сервісні функції і працює з БД напряму через власні сесії (`SessionLocal`). Тому бізнес-логіка (статуси інтервалів, avg_daily_km) — це спільні чисті функції у `backend/app/services/`, які викликаються і з роутерів API, і з бота, і з PDF-генератора.

Liveness probe: `GET /api/health` → `{"status": "ok"}`.

## 2.2 Технологічний стек з версіями

**Backend (`backend/requirements.txt`, Python 3.12-slim):**

| Пакет | Версія | Роль |
|---|---|---|
| fastapi | >=0.111,<1.0 | HTTP API |
| uvicorn[standard] | >=0.29,<1.0 | ASGI-сервер |
| sqlalchemy | >=2.0,<3.0 | ORM (стиль 2.0, `Mapped`/`mapped_column`) |
| pydantic / pydantic-settings | >=2.7 / >=2.2 | схеми API та конфіг з `.env` |
| PyJWT | >=2.8,<3.0 | JWT (HS256) |
| passlib[bcrypt] / bcrypt | ==1.7.4 / ==4.0.1 (запінено) | хешування паролів |
| python-multipart | >=0.0.9 | upload файлів (OCR) |
| psycopg2-binary | >=2.9,<3.0 | драйвер PostgreSQL |
| pytesseract / Pillow | >=0.3.10 / >=10,<12 | OCR чеків |
| aiogram | >=3.13,<4 | Telegram-бот |
| reportlab / pypdf | >=4.1 / >=4.2,<7 | PDF-звіт |
| pytest / httpx | >=8 / >=0.27 | тести (14 тест-файлів у `backend/tests/`) |

**Frontend (`frontend/package.json`):** react 18.3.1, react-dom 18.3.1, react-router-dom 6.26.2, axios 1.7.7, recharts 2.12.7 (графіки), zustand 4.5.5 (стан), lucide-react 0.452.0 (іконки); dev: vite 5.4.8, vite-plugin-pwa 0.20.5 (`registerType: 'autoUpdate'`, manifest name "Kapot Tracker"), tailwindcss 3.4.13, vitest 2.1.2. Збірка: node:20-alpine → nginx:alpine. БД у compose: postgres:16-alpine.

## 2.3 Ключові алгоритми

### 2.3.1 Розхід палива методом full-to-full (`app/services/fuel.py`, `compute_fuel_stats`)

Вхід — послідовність `RefuelPoint(date, odometer, liters, total_cost, is_full_tank)`; захисне сортування за `(odometer, date)`. Розхід вимірюється **тільки між двома послідовними заправками «до повного»** (`is_full_tank=True`):

1. Заправки **до першої повної** ігноруються (їх не можна виміряти — невідомий рівень бака).
2. Перша повна заправка стає «якорем» (anchor) сегмента.
3. Усі наступні заправки (часткові й повна, що закриває сегмент) **акумулюють літри і вартість** у поточний сегмент.
4. Коли трапляється наступна повна: `distance_km = point.odometer − anchor.odometer`. Якщо `distance_km > 0` і `accumulated_liters > 0` — сегмент валідний:
   `consumption_l_100km = accumulated_liters / distance_km × 100` (округлення до 2 знаків).
5. **Крайовий випадок:** сегмент з нульовою/від'ємною дистанцією (два записи на одному одометрі) просто пропускається, але повна заправка **все одно стає новим якорем**, а акумулятори скидаються — тобто один «битий» запис не ламає наступні сегменти.
6. Агрегати рахуються лише по валідних сегментах: `avg_consumption_l_100km = Σliters / Σkm × 100` (2 знаки), `avg_cost_per_km = Σcost / Σkm` (4 знаки); якщо валідних сегментів немає (`total_km == 0`) — обидва `None` (ділення на нуль неможливе). `last_consumption_l_100km` — розхід останнього сегмента, або `None`.

Результат віддається у `GET /api/cars/{car_id}/analytics` у блоці `fuel` разом з `history[]` (по кожному сегменту: `date, odometer, distance_km, liters, consumption_l_100km`).

### 2.3.2 Статус сервісного інтервалу (`app/services/intervals.py`, `compute_interval_status`)

Модель `ServiceInterval`: `title`, `interval_km`, `interval_days`, `last_odometer`, `last_date`, `last_notified_at` (усі, крім title, nullable; API вимагає хоча б одне з `interval_km`/`interval_days`). Обчислювані поля (віддаються в `GET /api/cars/{car_id}/intervals`):

- `due_odometer = last_odometer + interval_km` (тільки якщо задані обидва, інакше `None`);
- `due_date = last_date + interval_days` (аналогічно);
- `km_left = due_odometer − current_odometer` (може бути від'ємним);
- `days_left = (due_date − today).days` (може бути від'ємним);
- `predicted_due_date` — мінімум із двох кандидатів: (а) `today + km_left / avg_daily_km` днів (тільки якщо `avg_daily_km > 0`; `OverflowError` при майже нульовому темпі перехоплюється — кандидат просто не додається) і (б) `due_date`. Тобто **календарний дедлайн «виграє», якщо настає раніше за прогноз по пробігу**. Якщо кандидатів немає — `None`;
- `health_pct` — залишкова частка **жорсткішого** з двох лімітів: `min(km_left/interval_km, days_left/interval_days) × 100`, обрізається у діапазон [0, 100], округлення до 1 знака. Якщо жодної частки немає — `100.0`;
- `status` (пороги):
  - `overdue`, якщо `km_left < 0` **або** `days_left < 0`;
  - `due_soon`, якщо `health_pct < 15.0` **або** `km_left < 1000` **або** `days_left < 14`;
  - інакше `ok`.

### 2.3.3 Середній добовий пробіг (`compute_avg_daily_km`)

Береться перший і останній лог за сортуванням `(date, odometer)`: `avg_daily_km = (last.odometer − first.odometer) / (last.date − first.date).days`. **Фолбеки на константу `DEFAULT_AVG_DAILY_KM = 40.0`:** менше 2 логів; span дат < 1 дня (це також захист від ділення на нуль, коли всі логи в один день); неплюсова дельта одометра. Значення повертається у `CarOut.avg_daily_km` (округлення до 1 знака) і живить прогнози інтервалів у API, боті та PDF.

### 2.3.4 Прогнозна аналітика (`app/services/forecast.py`, блок `forecast` в analytics)

- **`monthly_km_rate`** = `round(odometer_delta / day_span × 30.0, 1)` по першому/останньому логу. `None`, якщо: < 2 логів, span < 7 днів, або дельта ≤ 0.
- **`avg_monthly_spend`** — середнє `total_cost` по **повних календарних місяцях**: місяці ≥ поточного (`(year, month) >= current`) відкидаються; з місяців, де є хоч один лог, беруться до `MAX_SPEND_MONTHS = 6` найсвіжіших; середнє їхніх сум, 2 знаки. `None`, якщо жодного повного місяця з даними.
- **`projected_month_total`** — прогноз витрат поточного місяця: `spent_this_month + daily_rate × remaining_days`, де `daily_rate = (сума витрат за вікно останніх SPEND_WINDOW_DAYS = 90 днів) / 90`, `remaining_days = днів_у_місяці − today.day`. `None`, якщо у 90-денному вікні немає жодного лога.
- **`estimate_interval_cost(interval_title, logs)`** — оцінка вартості майбутнього ТО через збіг ключових слів:
  1. `normalize_keywords`: токени `\w+` у нижньому регістрі, довжина ≥ `MIN_KEYWORD_LENGTH = 4`, мінус стоп-слова `UKRAINIAN_STOP_WORDS` (26 слів: «заміна», «замінити», «замінено», «перевірка», «ремонт», «огляд», «обслуговування», «встановлення», «кожні», «після», «новий», «робота» тощо — генеричні сервісні слова, які інакше зв'язали б кожен інтервал «Заміна …» з кожним записом про будь-яку заміну).
  2. Лог типу `maintenance`/`repair` вважається збігом, якщо його текст (`maintenance.items[]` + `repair.category` + `repair.part_name` + `notes`) має ≥ 1 спільне нормалізоване слово з назвою інтервалу.
  3. Результат — **медіана** `total_cost` збігів (2 знаки); `None`, якщо збігів немає або назва не дала ключових слів.
- **`upcoming[]`** — інтервали, що потрапляють у прогноз: `status ∈ {due_soon, overdue}` **або** `predicted_due_date ≤ today + UPCOMING_HORIZON_DAYS (90 днів)`. Сортування за `predicted_due_date` (елементи з `None` — у кінці). Поля елемента: `interval_id, title, predicted_due_date, km_left, days_left, estimated_cost`.

### 2.3.5 OCR-парсер чеків АЗС (`app/services/ocr.py` + `POST /api/ocr/scan`)

Ендпоінт: multipart-фото; тільки `image/*` (інакше 415); ліміт 10 МБ — перевіряється спершу `file.size`, потім читається щонайбільше `MAX_UPLOAD_BYTES + 1` байтів (413 при перевищенні, пам'ять не роздувається); 503 з підказкою по інсталяції, якщо бінарник tesseract відсутній.

**Розпізнавання тексту:** Pillow grayscale → `pytesseract.image_to_string(lang="ukr+eng", config="--psm 6")` («один суцільний блок тексту» — чек є вузькою колонкою, автосегментація рве рядок відпуску пального). Фолбек на `lang="eng"`, якщо немає ukr-traineddata.

**Парсинг (`parse_receipt_text`, чиста функція):**
- **Літри:** число + маркер `л`/`l` (регістронезалежно), lookbehind `(?<![\d.,/])` не дає матчитись усередині числа чи після «/» (щоб «грн/л» не зловився). Санітарний ліміт: `0 < liters ≤ MAX_LITERS = 200` (усе більше — OCR-хиба: серійні номери, купони).
- **Ціна за літр:** патерн `число [грн] / л`, або рядок з міткою «ціна» → перше число на ньому.
- **Фіскальний рядок «кількість X ціна»** (`40,45 X 19,99`, роздільник `[xх×*]` — латинський/кириличний x, «×», «*»): використовується **тільки якщо маркера літрів ніде немає** (магазинні позиції мають ту саму форму «Кава 2 x 35,00»); той самий ліміт ≤ 200 л.
- **Сума:** ключові слова в порядку пріоритету `TOTAL_KEYWORDS = ("до сплати", "сума", "разом", "total", "плат", "сплачено")` («плат»/«сплачено» — останні, бо картковий платіж може перевищувати підсумок або бути частиною split-оплати). Перед пошуком — **фолдинг латинських двійників** через мапу `"abcehikmoptxy" → "авсенікмортху"` (tesseract читає «СУМА» як "CYMA", «КАРТ» як "KAPT"). З рядка попередньо вирізаються токени «ГРН/Л». Якщо відомі літри та ціна — сума **заякорюється**: серед кандидатів беруться лише ті, що в діапазоні `[0.5 × liters×price; 1.02 × liters×price]` (знижки бувають, але не 50%; ratio — константи `_TOTAL_MIN_RATIO`/`_TOTAL_MAX_RATIO`), і обирається найближчий до брутто; інакше — **максимальне** число на рядках найпріоритетнішого ключового слова (менші числа там — ПДВ чи кількість).
- **Дата:** `dd.mm.yyyy` (роздільники `./-`); фолбек `dd-mm-yy` → рік `2000+yy`, приймається **тільки якщо ≤ сьогодні** (чек не може бути з майбутнього).
- **Бренд АЗС:** 12 брендів з латинськими і кириличними написаннями: OKKO, WOG, SOCAR, UPG, SHELL, AMIC, БРСМ, АВІАС, УКРНАФТА, KLO, MOTTO, MARSHAL; пошук по нижньому регістру та по фолднутому тексту з межею слова на початку.
- **Числа:** підтримуються групування тисяч пробілом/NBSP (`1 250.50`), крапкою (`1.250,50`) і комою (`1,250.50`); десяткова кома нормалізується у крапку; голе `1.250` = 1.25.
- **Обчислення третьої величини (`_fill_missing_third`):** якщо відомі рівно 2 з трійки (liters, price_per_liter, total_cost), третя добудовується: `total = liters × price` (2 знаки), `price = total / liters`, `liters = total / price`.

Відповідь `OcrScanResult`: `liters, price_per_liter, total_cost, date, gas_station, raw_text` (сирий текст повертається завжди — фронтенд показує форму для підтвердження/виправлення, автозапису немає).

### 2.3.6 Telegram link-codes і логіка бота

**Прив'язка акаунта:** `POST /api/telegram/link-code` (потрібен access-токен) видає **окремий короткоживучий JWT**: payload `{"sub": str(user_id), "purpose": "tg-link", "exp": now + LINK_CODE_EXPIRE_MINUTES (15 хв)}`, підписаний тим самим `SECRET_KEY` (HS256). Додатково — deep link `https://t.me/<TELEGRAM_BOT_USERNAME>?start=<code>`, якщо username налаштований.

**Двостороння ізоляція токенів:** (1) `decode_link_code` вимагає `purpose == "tg-link"`, тому access-токен **не приймається як код прив'язки**; (2) `get_current_user` в `auth.py` **відхиляє будь-який JWT, у якому є claim `purpose`**, тому link-код не можна використати як access-токен для API. Обидва напрямки підміни закриті, хоча ключ підпису спільний.

Бот на `/start <код>` викликає `link_user_by_code`: декодує код, записує `str(chat.id)` у `users.telegram_chat_id`; chat_id унікальний на рівні логіки застосунку — якщо цей чат уже був прив'язаний до іншого користувача, старий зв'язок обнуляється (re-link). `GET /api/telegram/status` → `{linked: bool}`; `DELETE /api/telegram/link` → 204 (відв'язка з веба); у боті є `unlink_chat`.

**Парсери повідомлень (`app/bot/parsers.py`, чисті функції):** `parse_odometer` — ціле число `1..2 000 000`, повний матч (десяткові, знаки, слова навколо — відхиляються); `parse_quick_expense` — `"<назва> <сума>"` (напр. «мийка 300», «омивайка 150,50»), десяткова кома нормалізується, ≤ 2 знаків після коми, сума > 0; голе число ніколи не є витратою (це пробіг). Оновлення пробігу **forward-only**: значення менше поточного відхиляється з поясненням. Швидка витрата створює `LogEntry(type="expense", date=today, odometer=current_odometer, notes=<назва>)`. При кількох авто — inline-клавіатура вибору (`callback_data` `odo:<car_id>:<value>` / `exp:<car_id>:<amount>`; назва витрати кешується в пам'яті процесу через 64-байтний ліміт callback data). `/status` — по кожному авто пробіг + топ-3 інтервалів, відсортованих за зростанням `health_pct`.

**Нагадування (`app/bot/reminders.py`):** фоновий цикл — перший прохід через 60 с після старту, далі кожні 24 год. Кандидати: користувачі з `telegram_chat_id`, інтервали зі статусом `due_soon`/`overdue`, у яких `last_notified_at` NULL або старіший за `NOTIFY_COOLDOWN_DAYS = 7` днів. Одне агреговане повідомлення на користувача, згруповане по авто; `last_notified_at` штампується **тільки після успішної відправки**; кожен користувач у своєму try/except (заблокований бот не зупиняє розсилку іншим). До нагадування додається «nudge» про пробіг, якщо останній лог старший за `NUDGE_AFTER_DAYS = 7` днів — окремо nudge ніколи не надсилається.

## 2.4 Авторизація і безпека

- **Паролі:** bcrypt через `passlib.CryptContext(schemes=["bcrypt"])`; версії запінені (`passlib==1.7.4` + `bcrypt==4.0.1`) через відому несумісність passlib з bcrypt ≥ 4.1.
- **JWT:** HS256, payload `{"sub": str(user_id), "exp": ...}`. `ACCESS_TOKEN_EXPIRE_MINUTES`: дефолт у коді 43200 (30 діб — зручно для PWA), у docker-compose дефолт 60. `SECRET_KEY` з env (dev-дефолт `dev-secret-change-me`). Логін: `POST /api/auth/token` (OAuth2 password form; email обрізається і переводиться в нижній регістр), реєстрація `POST /api/auth/register` (409-подібний 400 при дублі email), профіль `GET /api/auth/me`.
- **`get_current_user`:** декодує Bearer-токен, відхиляє токени з claim `purpose` (див. 2.3.6), парсить `sub` як int, шукає користувача в БД; будь-яка помилка → 401 з `WWW-Authenticate: Bearer`. Refresh-токенів, ролей, rate-limiting і token-revocation **немає**.
- **Ownership-скоупінг на кожному роуті:** три хелпери — `get_owned_car(db, user, car_id)` (`WHERE Car.id = ? AND Car.user_id = user.id`), `get_owned_log` та `get_owned_interval` (обидва через `JOIN cars` з фільтром `Car.user_id`). Чужий або неіснуючий ресурс дає однаковий **404** (без витоку існування, немає 403). Через ці хелпери проходять усі роути cars/logs/intervals/analytics/reports; `POST /api/ocr/scan` вимагає лише автентифікації (не прив'язаний до авто). У боті ownership перевіряється у callback-хендлерах через `get_car(db, user, car_id)`.
- **CORS:** allowlist з `CORS_ORIGINS` (кома-розділений рядок, дефолт `http://localhost:5173`), `allow_credentials=True`.
- Інваріант одометра: `POST/PATCH` лога з `odometer > car.current_odometer` пересуває одометр авто вперед (назад — ніколи); бот теж forward-only.

## 2.5 Стартова міграція `ensure_schema` (`app/migrations.py`)

Alembic не використовується. На старті **обох** процесів (lifespan API у `app/main.py` і `main()` бота у `app/bot/main.py`) виконується: (1) `Base.metadata.create_all(bind=engine)` — створює відсутні таблиці; (2) `ensure_schema(engine)` — легка адитивна міграція для баз, створених до Stage 2. Механізм: список `EXPECTED_COLUMNS = (("users", "telegram_chat_id", "VARCHAR(50)"), ("service_intervals", "last_notified_at", "DATE"))`; через SQLAlchemy `inspect` перевіряється жива схема, і для відсутніх колонок виконується сирий `ALTER TABLE <table> ADD COLUMN <column> <type>`. Типи підібрані так, щоб їх приймали і SQLite, і PostgreSQL. Функція ідемпотентна (безпечна при кожному старті й при конкурентному старті API+бот: існуючі колонки не чіпаються, відсутні таблиці пропускаються — їх щойно створив `create_all` з повною схемою). Обмеження підходу: тільки додавання колонок; перейменування/видалення/зміна типів не підтримуються.

---

## 3. Довідник API і схема даних

Цей розділ — повний самодостатній контракт бекенду Kapot Tracker (FastAPI, файли `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/routers/*`). Усі шляхи мають префікс `/api` (роутери підключаються в `backend/app/main.py` з `prefix="/api"`). БД: SQLite за замовчуванням (`sqlite:///./kapot_tracker.db`), PostgreSQL у Docker (`postgresql+psycopg2`). Міграцій Alembic немає: на старті виконується `Base.metadata.create_all` плюс легкі адитивні міграції `ensure_schema()` (`backend/app/migrations.py`), які додають відсутні колонки `users.telegram_chat_id VARCHAR(50)` і `service_intervals.last_notified_at DATE` через `ALTER TABLE ... ADD COLUMN`. У dev-базі (`backend/kapot_tracker.db`) засіяно реальну історію VW Golf 7 Variant 1.6 TDI власника: 19 записів журналу, 7 сервісних інтервалів, 87 323 грн задокументованих витрат.

## 3.1. Схема бази даних

Валюта ніде не зберігається — всі грошові поля неявно у гривнях (мультивалютність — ідея Етапу 4). Грошові значення пишуться як `Numeric` через `Decimal(str(value))`, щоб уникнути двійкових артефактів float.

### Таблиця `users`
| Поле | Тип | Обмеження |
|---|---|---|
| `id` | INTEGER | PK |
| `email` | VARCHAR(255) | UNIQUE, INDEX, NOT NULL |
| `hashed_password` | VARCHAR(255) | NOT NULL (bcrypt через passlib) |
| `telegram_chat_id` | VARCHAR(50) | NULL. Унікальність — лише логікою застосунку: привʼязка того самого chat_id до іншого користувача спершу очищає старий запис (немає UNIQUE-констрейнта в БД) |
| `created_at` | DATETIME | NOT NULL, default UTC now |

Звʼязок: `users 1—N cars` (ORM cascade `all, delete-orphan`; FK з `ondelete="CASCADE"`).

### Таблиця `cars`
| Поле | Тип | Обмеження |
|---|---|---|
| `id` | INTEGER | PK |
| `user_id` | INTEGER | FK → `users.id` ON DELETE CASCADE, INDEX, NOT NULL |
| `brand` | VARCHAR(100) | NOT NULL |
| `model` | VARCHAR(100) | NOT NULL |
| `generation` | VARCHAR(100) | NULL |
| `engine` | VARCHAR(100) | NULL |
| `year` | INTEGER | NOT NULL (API: 1950–2100) |
| `fuel_type` | VARCHAR(20) | NOT NULL; значення (Literal в API): `diesel`, `petrol`, `lpg`, `electric`, `hybrid` |
| `current_odometer` | INTEGER | NOT NULL, default 0 |
| `created_at` | DATETIME | NOT NULL, default UTC now |

Звʼязки: `cars 1—N log_entries`, `cars 1—N service_intervals` (обидва cascade delete).

### Таблиця `log_entries`
| Поле | Тип | Обмеження |
|---|---|---|
| `id` | INTEGER | PK |
| `car_id` | INTEGER | FK → `cars.id` ON DELETE CASCADE, INDEX, NOT NULL |
| `type` | VARCHAR(20) | NOT NULL, INDEX; значення: `refuel`, `maintenance`, `repair`, `expense` |
| `odometer` | INTEGER | NOT NULL (API: ≥ 0) |
| `date` | DATE | NOT NULL, INDEX |
| `total_cost` | NUMERIC(10,2) | NOT NULL, default 0 (API: ≥ 0) |
| `notes` | TEXT | NULL |
| `created_at` | DATETIME | NOT NULL, default UTC now |

До кожного запису опційно приєднується РІВНО ОДИН деталь-рядок 1:1 (PK = FK), який відповідає його `type`. Тип `expense` деталь-таблиці не має.

### Таблиця `refuel_details` (1:1 до `log_entries`)
| Поле | Тип | Обмеження |
|---|---|---|
| `log_entry_id` | INTEGER | PK, FK → `log_entries.id` ON DELETE CASCADE |
| `liters` | NUMERIC(6,2) | NOT NULL (API: > 0) |
| `price_per_liter` | NUMERIC(6,2) | NOT NULL (API: ≥ 0) |
| `is_full_tank` | BOOLEAN | NOT NULL, default true — ключове поле для методу «повний-до-повного» |
| `gas_station` | VARCHAR(200) | NULL |

### Таблиця `maintenance_details` (1:1)
| Поле | Тип | Обмеження |
|---|---|---|
| `log_entry_id` | INTEGER | PK, FK → `log_entries.id` ON DELETE CASCADE |
| `parts_cost` | NUMERIC(10,2) | NOT NULL, default 0 (API: ≥ 0) |
| `labor_cost` | NUMERIC(10,2) | NOT NULL, default 0 (API: ≥ 0) |
| `items` | JSON | NOT NULL, default `[]` — список рядків («Мастило 5W-30», «Фільтр оливний»...) |

### Таблиця `repair_details` (1:1)
| Поле | Тип | Обмеження |
|---|---|---|
| `log_entry_id` | INTEGER | PK, FK → `log_entries.id` ON DELETE CASCADE |
| `category` | VARCHAR(100) | NOT NULL |
| `part_name` | VARCHAR(200) | NULL |
| `warranty_months` | INTEGER | NULL (API: ≥ 0) |
| `warranty_km` | INTEGER | NULL (API: ≥ 0) |

### Таблиця `service_intervals`
| Поле | Тип | Обмеження |
|---|---|---|
| `id` | INTEGER | PK |
| `car_id` | INTEGER | FK → `cars.id` ON DELETE CASCADE, INDEX, NOT NULL |
| `title` | VARCHAR(200) | NOT NULL |
| `interval_km` | INTEGER | NULL (API: > 0) |
| `interval_days` | INTEGER | NULL (API: > 0); інваріант API: хоча б одне з `interval_km`/`interval_days` мусить бути задане |
| `last_odometer` | INTEGER | NULL (API: ≥ 0) |
| `last_date` | DATE | NULL |
| `last_notified_at` | DATE | NULL — штамп останнього Telegram-нагадування; кулдаун `NOTIFY_COOLDOWN_DAYS = 7` днів |

### Запланована таблиця `log_photos` (ітерація «повне редагування» — СПРОЕКТОВАНО, НЕ РЕАЛІЗОВАНО)
Коду цієї таблиці в репозиторії ще немає; це дизайн-намір для фічі «фото-вкладення до запису» на майбутній сторінці деталей `/logbook/:id`. Орієнтовна структура за аналогією з наявними деталь-таблицями: `id` INTEGER PK; `log_entry_id` INTEGER FK → `log_entries.id` ON DELETE CASCADE, INDEX; поле збереження файла (шлях/імʼя на диску або обʼєкт-сторедж — рішення про сторедж не зафіксоване, Етап 4 у README згадує S3/MinIO); `content_type` (image/*); `size_bytes`; `created_at`. Разом з нею ітерація додає: режим редагування запису (PATCH `/api/logs/{log_id}` вже існує на бекенді — фронтенд його ще не використовує повністю), редагування інтервалів (PATCH `/api/intervals/{interval_id}` теж уже існує), пошук по журналу, віджет швидкого оновлення пробігу та дублювання запису. Тобто бекенд-контракт для редагування ГОТОВИЙ, нова тільки `log_photos` і, ймовірно, ендпоінти виду `POST/GET/DELETE /api/logs/{log_id}/photos`.

## 3.2. Автентифікація та формат помилок

- **JWT** HS256, `SECRET_KEY` з env (дефолт `dev-secret-change-me`). Access-токен: payload `{"sub": "<user_id>", "exp": ...}`, термін дії `ACCESS_TOKEN_EXPIRE_MINUTES` (дефолт у коді **43200 хв = 30 діб**). Заголовок: `Authorization: Bearer <token>`, tokenUrl `/api/auth/token`.
- Токени зі claim `purpose` (наприклад, Telegram link-код з `purpose="tg-link"`) **не** приймаються як access-токени → 401.
- Будь-який захищений ендпоінт без/з невалідним токеном → **401** `{"detail": "Could not validate credentials"}` + `WWW-Authenticate: Bearer`.
- Формат помилок — стандарт FastAPI `{"detail": ...}`, АЛЕ `detail` буває двох форм: (а) **масив обʼєктів** pydantic для автоматичної 422-валідації тіла (`[{"loc": ..., "msg": ..., "type": ...}]`); (б) **простий рядок** для ручних HTTPException, включно з кастомними 422 із роутерів logs/intervals (напр. `"Invalid log type 'fuel'"`, `"Incomplete detail object: Field required"`). Клієнт мусить обробляти обидві форми.
- Ізоляція даних: усі ресурси чужих користувачів відповідають **404** (не 403) — `"Car not found"`, `"Log entry not found"`, `"Service interval not found"`.
- CORS: список origin-ів з `CORS_ORIGINS` (дефолт `http://localhost:5173`).

## 3.3. Повний довідник REST API

### Група `/api/auth`
| Метод і шлях | Тіло запиту | Відповідь 2xx | Помилки |
|---|---|---|---|
| `POST /api/auth/register` | JSON `{email, password}`; email 3–255 симв.,ترim+lowercase, формат `local@domain` з крапкою в домені; password 6–128 | **201** `{id, email, created_at}` | 400 `"Email already registered"`; 422 (масив pydantic) |
| `POST /api/auth/token` | **form-urlencoded** (OAuth2PasswordRequestForm): `username` (=email), `password` | **200** `{access_token, token_type: "bearer"}` | 401 `"Incorrect email or password"` |
| `GET /api/auth/me` | — | **200** `{id, email, created_at}` | 401 |

### Група `/api/cars`
`CarOut` (відповідь усюди): `{id, brand, model, generation, engine, year, fuel_type, current_odometer, avg_daily_km, created_at}`. Поле `avg_daily_km` — обчислюване (див. 3.5), округлене до 1 знака.

| Метод і шлях | Тіло запиту | Відповідь | Помилки |
|---|---|---|---|
| `GET /api/cars` | — | **200** `[CarOut]` (сортування за id) | 401 |
| `POST /api/cars` | `{brand, model, generation?, engine?, year, fuel_type, current_odometer}`; brand/model 1–100; year 1950–2100; fuel_type ∈ diesel/petrol/lpg/electric/hybrid; current_odometer ≥ 0 | **201** `CarOut` | 401; 422 |
| `GET /api/cars/{car_id}` | — | **200** `CarOut` | 401; 404 |
| `PATCH /api/cars/{car_id}` | ті самі поля, всі опційні (partial update, `exclude_unset`) | **200** `CarOut` | 401; 404; 422 |
| `DELETE /api/cars/{car_id}` | — | **204** (каскадно видаляє logs та intervals) | 401; 404 |

### Журнал (роутер logs)
`LogEntryOut`: `{id, car_id, type, odometer, date, total_cost, notes, refuel, maintenance, repair, created_at}`, де `refuel = {liters, price_per_liter, is_full_tank, gas_station} | null`, `maintenance = {parts_cost, labor_cost, items} | null`, `repair = {category, part_name, warranty_months, warranty_km} | null`.

| Метод і шлях | Тіло/параметри запиту | Відповідь | Помилки |
|---|---|---|---|
| `GET /api/cars/{car_id}/logs` | query: `type?` (refuel/maintenance/repair/expense), `limit` (default 50, 1–500), `offset` (default 0, ≥0) | **200** `{items: [LogEntryOut], total: int}`; сортування `date DESC, odometer DESC`; `total` — кількість з урахуванням фільтра, без пагінації | 401; 404; **422 з рядковим detail** `"Invalid log type '<type>'"` |
| `POST /api/cars/{car_id}/logs` | `{type, odometer (≥0), date, total_cost (≥0), notes?, refuel?, maintenance?, repair?}`. Model-validator: `type="refuel"` вимагає обʼєкт `refuel`; `type="maintenance"` вимагає `maintenance`; для `type="repair"` обʼєкт `repair` **опційний**; для `expense` деталей немає. Деталь, що не відповідає `type`, мовчки ігнорується | **201** `LogEntryOut`. **Побічний ефект:** якщо `odometer > car.current_odometer` — пробіг авто підтягується вперед | 401; 404; 422 |
| `PATCH /api/logs/{log_id}` | усі поля опційні: `{type?, odometer?, date?, total_cost?, notes?, refuel?, maintenance?, repair?}`; вкладені деталі теж partial | **200** `LogEntryOut`. Ті самі побічні ефекти на пробіг | 401; 404 `"Log entry not found"`; 422 (див. 3.5) |
| `DELETE /api/logs/{log_id}` | — | **204** (деталь-рядок видаляється каскадно). Пробіг авто НЕ відкочується | 401; 404 |

### Сервісні інтервали (роутер intervals)
`IntervalStatusOut` (відповідь усюди): збережені поля `{id, car_id, title, interval_km, interval_days, last_odometer, last_date}` + **обчислені** `{due_odometer, due_date, km_left, days_left, predicted_due_date, health_pct, status}` (формули в 3.4; `status ∈ ok | due_soon | overdue`).

| Метод і шлях | Тіло запиту | Відповідь | Помилки |
|---|---|---|---|
| `GET /api/cars/{car_id}/intervals` | — | **200** `[IntervalStatusOut]` (за id) | 401; 404 |
| `POST /api/cars/{car_id}/intervals` | `{title (1–200), interval_km? (>0), interval_days? (>0), last_odometer? (≥0), last_date?}`; model-validator: хоча б одне з `interval_km`/`interval_days` | **201** `IntervalStatusOut` | 401; 404; 422 |
| `PATCH /api/intervals/{interval_id}` | ті самі поля, всі опційні | **200** `IntervalStatusOut` | 401; 404 `"Service interval not found"`; **422 з рядковим detail** `"at least one of interval_km or interval_days is required"`, якщо після злиття обидва поля стали null (робиться rollback) |
| `DELETE /api/intervals/{interval_id}` | — | **204** | 401; 404 |

### Аналітика
| Метод і шлях | Відповідь |
|---|---|
| `GET /api/cars/{car_id}/analytics` | **200** `AnalyticsOut` (401/404 стандартно) |

Структура `AnalyticsOut` (усі суми округлені до 2 знаків):
```
{
  totals: { all_time, this_month, by_type: { refuel, maintenance, repair, expense } },
  monthly: [ { month: "YYYY-MM", refuel, maintenance, repair, expense, total } ] // рівно 12 останніх календарних місяців включно з поточним, від найстарішого,
  fuel: {
    avg_consumption_l_100km | null, last_consumption_l_100km | null,
    avg_cost_per_km | null (4 знаки),
    history: [ { date, odometer, distance_km, liters, consumption_l_100km } ]
  },
  forecast: {
    monthly_km_rate | null, avg_monthly_spend | null, projected_month_total | null,
    upcoming: [ { interval_id, title, predicted_due_date | null, km_left | null, days_left | null, estimated_cost | null } ]
  }
}
```

### PDF-звіт
| Метод і шлях | Відповідь |
|---|---|
| `GET /api/cars/{car_id}/report` | **200**, `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="kapot-tracker-report-{car_id}.pdf"` (ASCII-імʼя). Генерація reportlab із вбудованими шрифтами DejaVu (кирилиця), мова — українська: дані авто, пробіг, підсумки витрат, повна сервісна історія, зведення заправок, таблиця інтервалів. Авто без записів усе одно рендерить валідний PDF. 401/404 стандартно |

### OCR чека
| Метод і шлях | Запит | Відповідь | Помилки |
|---|---|---|---|
| `POST /api/ocr/scan` | `multipart/form-data`, поле **`file`** — зображення чека | **200** `{liters, price_per_liter, total_cost, date, gas_station, raw_text}` — усі поля крім `raw_text` можуть бути null | 401; **415** `"Only image uploads are supported"` (Content-Type не image/*); **413** `"Image is too large (max 10 MB)"` (ліміт 10 МБ = 10·1024·1024 байт, перевіряється і по заявленому розміру, і по фактичному читанню limit+1); **503**, якщо бінарник tesseract не встановлено (решта API при цьому працює) |

Пайплайн OCR: grayscale → tesseract `lang="ukr+eng"`, `--psm 6` (фолбек на eng, якщо немає ukr traineddata) → чистий парсер `parse_receipt_text`: літри за маркером «л/L», фіскальний рядок «кількість X ціна», ключові слова суми (`до сплати`, `сума`, `разом`, `total`, `плат`, `еквайринг`, `сплачено`), згортання латинських двійників кирилиці (CYMA→СУМА), санітарний ліміт 200 л, дати `dd.mm.yyyy` та `dd-mm-yy`, бренд АЗС зі словника: OKKO, WOG, SOCAR, UPG, SHELL, AMIC, БРСМ, АВІАС, УКРНАФТА, KLO, MOTTO, MARSHAL. Якщо знайдено рівно два з трійки (liters, price_per_liter, total_cost) — третє дообчислюється (`total = liters·price` тощо).

### Група `/api/telegram`
| Метод і шлях | Відповідь | Примітки |
|---|---|---|
| `POST /api/telegram/link-code` | **200** `{code, deep_link, expires_in_minutes}` | `code` — JWT з `purpose="tg-link"`, живе `LINK_CODE_EXPIRE_MINUTES` (дефолт 15 хв); `deep_link` = `https://t.me/{TELEGRAM_BOT_USERNAME}?start={code}` або null, якщо username не сконфігуровано |
| `GET /api/telegram/status` | **200** `{linked: bool}` | true, коли `users.telegram_chat_id` не null |
| `DELETE /api/telegram/link` | **204** | очищає `telegram_chat_id` |

Важливо: сам бот НЕ має REST-ендпоінтів (жодного webhook) — він працює long-polling-ом окремим процесом (`python -m app.bot.main`, docker-профіль `bot`) і пише в БД напряму через той самий SQLAlchemy-шар (`backend/app/bot/service.py`).

### Службове
| Метод і шлях | Відповідь |
|---|---|
| `GET /api/health` | **200** `{"status": "ok"}` — без авторизації, liveness-проба |

## 3.4. Формули обчислюваних полів

**`avg_daily_km` (авто)** — `(odometer_останнього_лога − odometer_першого_лога) / днів_між_ними` за першим/останнім записом журналу, відсортованим за `(date, odometer)`. Потрібні ≥2 записи, проміжок ≥1 день і додатна дельта пробігу; інакше фолбек `DEFAULT_AVG_DAILY_KM = 40.0`.

**Статус інтервалу** (`backend/app/services/intervals.py`):
- `due_odometer = last_odometer + interval_km` (якщо обидва задані), `due_date = last_date + interval_days` днів.
- `km_left = due_odometer − car.current_odometer`; `days_left = due_date − today`.
- `predicted_due_date = min(today + km_left/avg_daily_km днів; due_date)` — береться найближча з двох дат; null, якщо жодної.
- `health_pct = min(km_left/interval_km, days_left/interval_days) · 100`, клампиться в [0; 100], округлення до 1 знака; 100.0 при відсутності даних.
- `status`: `overdue`, якщо `km_left < 0` АБО `days_left < 0`; інакше `due_soon`, якщо `health_pct < 15` АБО `km_left < 1000` АБО `days_left < 14`; інакше `ok`.

**Розхід пального «повний-до-повного»** (`backend/app/services/fuel.py`): сегменти вимірюються тільки між двома послідовними заправками з `is_full_tank=true`; часткові заправки додають літри й вартість у наступний повний сегмент; заправки до першої «повної» ігноруються; сегмент з нульовою/відʼємною дистанцією пропускається, але повна заправка все одно стає новим якорем. `consumption_l_100km = liters/distance_km · 100`; `avg_consumption` — за сумою всіх виміряних сегментів; `avg_cost_per_km = сумарна вартість виміряних сегментів / сумарні км` (4 знаки).

**Forecast** (`backend/app/services/forecast.py`):
- `monthly_km_rate = дельта_пробігу / проміжок_днів · 30` (1 знак); null, якщо <2 записів, проміжок <7 днів або дельта ≤0.
- `avg_monthly_spend` — середнє сумарних витрат до 6 (`MAX_SPEND_MONTHS`) останніх ПОВНИХ календарних місяців, у яких є хоч один запис (поточний місяць виключено); null, якщо таких немає.
- `projected_month_total = витрачено_цього_місяця + (витрати_за_останні_90_днів / 90) · днів_до_кінця_місяця` (вікно `SPEND_WINDOW_DAYS = 90`); null, якщо у вікні немає записів.
- `upcoming` — інтервали зі статусом `due_soon`/`overdue` АБО з `predicted_due_date` в межах 90 днів (`UPCOMING_HORIZON_DAYS`), відсортовані за `predicted_due_date` (null-и в кінці).
- `estimated_cost` — **медіана** `total_cost` минулих maintenance/repair-записів цього авто, чий текст (items ТО, category/part_name ремонту, notes) має ≥1 спільне нормалізоване ключове слово з назвою інтервалу. Нормалізація: lowercase-токени довжиною ≥4 (`MIN_KEYWORD_LENGTH`), мінус український стоп-словник загальних сервісних слів («заміна», «перевірка», «ремонт», «огляд», «обслуговування» тощо — 27 слів). null, якщо збігів немає.

## 3.5. Правила валідації та побічні ефекти (повний перелік)

1. **Одометр авто рухається лише вперед.** `POST /api/cars/{id}/logs` і `PATCH /api/logs/{id}`: якщо `odometer` запису > `car.current_odometer` — пробіг авто оновлюється до цього значення; менше значення НЕ відкочує авто (запис зберігається як є). Видалення запису пробіг не відкочує. Telegram-бот при оновленні пробігу числом-повідомленням поводиться суворіше: значення, менше за поточне, взагалі відхиляється.
2. **Деталь відповідає типу.** При створенні зберігається тільки деталь-обʼєкт, що збігається з `type`; зайві ігноруються. `refuel` і `maintenance` без своєї деталі → 422 (pydantic model-validator); `repair` без деталі — дозволено; `expense` деталей не має.
3. **PATCH запису з неповною деталлю — 422 з РЯДКОВИМ detail.** Якщо PATCH передає деталь-обʼєкт для запису, в якого такого рядка ще немає, часткові поля мають складатися в повний create-payload; інакше 422 `"Incomplete detail object: <перше повідомлення pydantic>"` — це рядок, а не масив обʼєктів, на відміну від стандартної 422-валідації тіла. Аналогічні рядкові 422: `"Invalid log type '<type>'"` (фільтр списку), `"refuel details are required when type is 'refuel'"`, `"maintenance details are required when type is 'maintenance'"`, `"at least one of interval_km or interval_days is required"`.
4. **Зміна `type` через PATCH мовчки видаляє невідповідні деталь-рядки** (напр., refuel→expense стирає `refuel_details` без попередження), після чого інваріанти п.2 перевіряються знову.
5. **Ownership → 404.** Кожен car-scoped ресурс чужого користувача повертає 404, ідентичний неіснуючому — існування чужих ресурсів не розкривається.
6. **Каскади видалення:** user→cars→(log_entries→details, service_intervals) — на рівні FK `ondelete="CASCADE"` і ORM.
7. **JWT-гігієна:** link-код Telegram (JWT з `purpose="tg-link"`) не автентифікує API-запити (401); access-токен не працює як link-код (перевірка `purpose == "tg-link"` у `decode_link_code`).
8. **Побічні ефекти бота (без HTTP):** привʼязка chat_id відбирає його в попереднього користувача; «швидка витрата» (`мийка 300`) створює `log_entries` з `type="expense"`, `odometer = car.current_odometer`, `date = сьогодні`, `notes = назва`; нагадування ставлять `service_intervals.last_notified_at = сьогодні` і повторюються не частіше ніж раз на 7 днів на інтервал.
9. **Пагінація журналу:** `limit` 1–500 (дефолт 50), `offset ≥ 0`; відповідь завжди `{items, total}`, сортування фіксоване `date DESC, odometer DESC` (параметра сортування немає).
10. **Email нормалізується** (trim + lowercase) і при реєстрації, і при логіні; перевірка формату власна (не EmailStr): непорожні local і domain, крапка в domain.
11. **Числа з форм** конвертуються `Decimal(str(float))` перед записом у `Numeric` — у відповідях грошові поля серіалізуються як float.
12. **Схема створюється на старті** обох процесів (API lifespan і бот) — `create_all` + ідемпотентні `ALTER TABLE` з `EXPECTED_COLUMNS`; повноцінного інструмента міграцій немає, тому будь-яка нова таблиця (напр., майбутня `log_photos`) зʼявиться через `create_all`, а нові колонки існуючих таблиць треба додавати в `EXPECTED_COLUMNS`.

---

## 4. Фронтенд і UX

Фронтенд Kapot Tracker — це односторінковий React-застосунок (PWA), зібраний Vite, розташований у `frontend/`. Стек: **React 18.3** + **react-router-dom 6.26** + **zustand 4.5** (стейт) + **axios 1.7** (HTTP) + **Recharts 2.12** (графіки) + **lucide-react** (іконки) + **Tailwind CSS 3.4** (стилі) + **vite-plugin-pwa 0.20** (сервіс-воркер/маніфест) + **vitest** (юніт-тести утиліт `format.js`, `refuelMath.js`, `reports.js`). Уся мова інтерфейсу — українська, рядки зашиті прямо в JSX (i18n-фреймворку немає).

## 4.1. Карта екранів і маршрутів

Маршрутизація описана в `frontend/src/App.jsx`. Два guard-компоненти: `Protected` (без токена → redirect на `/login`) і `PublicOnly` (з токеном → redirect на `/`). Усі захищені маршрути рендеряться всередині спільного `Layout` (`frontend/src/components/Layout.jsx`). Будь-який невідомий шлях (`*`) → redirect на `/`.

| Маршрут | В'ю (файл) | Доступ |
|---|---|---|
| `/login` | `views/Login.jsx` | тільки без токена |
| `/register` | `views/Register.jsx` | тільки без токена |
| `/` | `views/Dashboard.jsx` | захищений |
| `/logbook` | `views/Logbook.jsx` | захищений |
| `/add` (+ `?type=`) | `views/AddEntry.jsx` | захищений |
| `/analytics` | `views/Analytics.jsx` | захищений |
| `/garage` | `views/Garage.jsx` | захищений |

### Layout (спільний каркас)
- **Верхній хедер** (sticky, `bg-slate-950/90 backdrop-blur`): логотип «Kapot Tracker» (іконка авто на синьому квадраті, клік веде на `/`), **CarSelector** — нативний `<select>` вибору активного авто (показує `brand model`, ховається якщо авто немає), кнопка виходу (LogOut-іконка, скидає стори).
- **Контент**: `main` з `mx-auto max-w-md px-4 pb-28 pt-4`; має `key={location.pathname}` — примусовий ремонт піддерева при зміні маршруту.
- **Нижня навігація** (fixed, 5 пунктів, `grid-cols-5`, враховує `env(safe-area-inset-bottom)`): Головна `/`, Журнал `/logbook`, **Додати `/add`** (центральна FAB-кнопка: коло 56×56 px, `bg-blue-600`, підняте на `-mt-8` над панеллю), Аналітика `/analytics`, Гараж `/garage`. Активний пункт — `text-blue-500`.

### Login / Register
Центрована картка з лого. Login: поля Email + Пароль, помилка через `extractError` («Невірний email або пароль» за замовчуванням), лінк на реєстрацію. Register: Email + Пароль + Повторіть пароль; клієнтська валідація — збіг паролів і мінімум 6 символів; після реєстрації одразу автологін і redirect на `/`.

### Dashboard (`/`)
- Порожній стан (немає авто): вітальна картка «Вітаємо в Kapot Tracker!» з CTA-кнопкою «Додати авто» → `/garage`.
- Заголовок: `brand model` активного авто + поточний пробіг (`current_odometer`).
- **3 стат-картки** з `analytics`: «Цей місяць» (`totals.this_month`, formatMoney), «л/100 км» (`fuel.avg_consumption_l_100km`, `.toFixed(1)`), «₴/км» (`fuel.avg_cost_per_km`, `.toFixed(2)`); якщо null — «—».
- **2 кнопки швидкої дії**: «Заправка» → `/add?type=refuel` (синя), «Витрата» → `/add?type=expense` (сіра).
- **Картка «Інтервали ТО»**: для кожного інтервалу — назва, статус-бейдж (`ok` → «В нормі», синій; `due_soon` → «Скоро», бурштиновий; `overdue` → «Прострочено», червоний), прогрес-бар «здоров'я» по `health_pct` (0–100, кольори ті самі), тексти «N км залишилось / прострочено», «N дн. / N дн. тому», «приблизно <дата>» з `predicted_due_date`. Лінк «Керувати» → `/garage`. Дій над інтервалами тут немає — тільки перегляд.

### Logbook (`/logbook`)
- **Фільтр-чипи** (горизонтальний скрол): Всі / Заправки (`refuel`) / ТО (`maintenance`) / Ремонт (`repair`) / Інше (`expense`). Фільтр — локальний `useState`, при зміні перезавантажує список з сервера (`GET /api/cars/:carId/logs?type=`).
- Список карток **LogTimelineItem** (`components/LogTimelineItem.jsx`): кольорова іконка типу, заголовок (для заправки — «Заправка · <АЗС>», для ТО — до 2 позицій `items` через кому + «…», для ремонту — «Ремонт · <категорія> · <деталь>», для витрати — «Витрата · <нотатки>»), дата + пробіг, для заправки — «X.X л × ціна/л · повний бак», сума праворуч, кнопка-смітник.
- **Видалення** — єдина дія над записом: `window.confirm('Видалити цей запис? Дію не можна скасувати.')` → `DELETE /api/logs/:id` → toast «Запис видалено»; помилка — `window.alert`.
- Пагінації як такої немає: завантажується перша сторінка `limit=50, offset=0`; якщо `total > items.length`, показується лише напис «Показано X з Y записів» **без кнопки "завантажити ще"**.
- Toast «Запис додано» приходить через `location.state.toast` (навігація з AddEntry) і очищається `navigate(..., {replace:true, state:null})`.
- **Чого НЕМАЄ**: перегляду деталей запису (немає маршруту `/logbook/:id`), **редагування запису** (функція `updateLog(logId, payload)` → `PATCH /api/logs/:id` існує в `api/logs.js`, але жоден компонент її не викликає), пошуку по журналу, дублювання запису, фото-вкладень. Усе це — спроєктована, але не реалізована ітерація «повного редагування».

### AddEntry (`/add`)
- Тип запису читається з query-параметра `?type=` (валідні: `refuel|maintenance|repair|expense`, дефолт `refuel`) і перемикається табами з 4 кнопок; зміна табу пише `setSearchParams({type}, {replace:true})`.
- **Спільні поля**: Дата (`date`, дефолт сьогодні), Пробіг км (`odometer`, автопідставляється `activeCar.current_odometer`), Загальна вартість ₴ (`total_cost`), Нотатки (`notes`).
- **Заправка**: Літри, Ціна за літр, Toggle «Повний бак» (`is_full_tank`, дефолт true), АЗС (`gas_station`). **Авто-математика** (`utils/refuelMath.js`, чиста функція `computeRefuelUpdate`): редагування будь-якого з трьох полів (літри/ціна/сума) обчислює третє з двох інших, десяткова кома толерується (`num()` замінює `,` на `.`), нульові/порожні значення не тригерять обчислення.
- **Сканування чека (OCR)**: кнопка «Сканувати чек» — `<input type="file" accept="image/*" capture="environment">` → `POST /api/ocr/scan` (multipart). Відповідь `{liters, price_per_liter, total_cost, date, gas_station, raw_text}` заповнює поля, **але не перезаписує поля, які користувач редагував під час скану** (механізм `editedDuringScanRef` — Set назв полів). Toast показує розпізнане («Розпізнано: 40 л, 54.99 грн/л, …»); HTTP 503 → «Розпізнавання недоступне на сервері».
- **ТО**: чекбокси «Що замінено» з 6 типових позицій (Олива двигуна, Масляний фільтр, Повітряний фільтр, Салонний фільтр, Паливний фільтр, Гальмівна рідина) + додавання власних позицій; поля «Запчастини ₴» (`parts_cost`) і «Робота ₴» (`labor_cost`) — сума автоматично пишеться в Загальну вартість.
- **Ремонт**: Select категорії (Підвіска, Гальма, Двигун, Електрика, Трансмісія, Кузов, Інше), Деталь (`part_name`), Гарантія міс. (`warranty_months`), Гарантія км (`warranty_km`).
- Сабміт: клієнтська валідація (дата, пробіг ≥ 0, вартість ≥ 0; для заправки літри > 0 і ціна > 0), `POST /api/cars/:carId/logs`, при успіху `navigate('/logbook', {state:{toast:'Запис додано'}})`.

### Analytics (`/analytics`)
- Кнопка **«Звіт PDF»** у хедері: `GET /api/cars/:carId/report` (`responseType:'blob'`) → браузерне завантаження файлу `kapot-tracker-report-<carId>.pdf` через тимчасовий object URL (`api/reports.js`).
- **Секція «Прогноз»** (`analytics.forecast`): 3 картки — «Середні витрати/міс» (`avg_monthly_spend`), «Прогноз на цей місяць» (`projected_month_total`), «Пробіг км/міс» (`monthly_km_rate`); картка «Найближчі ТО» — список `forecast.upcoming` (у межах 90 днів): назва, `predicted_due_date` та/або «через N км» (`km_left`), «~сума / орієнтовно» (`estimated_cost`).
- Картки підсумків: «Всього витрачено» (`totals.all_time`), «Цей місяць» (`totals.this_month`), легенда «За категоріями (весь час)» (`totals.by_type` по 4 типах).
- **Stacked BarChart «Витрати за місяцями, ₴»** (Recharts, висота 256 px): дані `analytics.monthly`, 4 серії — Заправки `#3987e5`, ТО `#199e70`, Ремонт `#c98500`, Інше `#9085e9` (палітра валідована для дальтонізму: CVD worst adjacent dE 41.3, контраст ≥ 3:1 на поверхні slate-900); вісь Y скорочує тисячі до «Nк»; кастомний темний тултіп.
- **LineChart «Витрата пального, л/100 км»** (висота 224 px): `analytics.fuel.history`, пунктирна ReferenceLine на середньому (`avg_consumption_l_100km`), підпис «середнє X.X»; під графіком — «Остання виміряна витрата: X.XX л/100 км». Порожній стан пояснює: потрібні щонайменше дві заправки «до повного».
- Жодних фільтрів періоду / вибору діапазону дат немає.

### Garage (`/garage`)
- **CRUD авто**: інлайн-форма `CarForm` (без модалки) з полями Марка (`brand`), Модель (`model`), Покоління (`generation`), Двигун (`engine`), Рік (`year`, 1900–2100), Пальне (`fuel_type`: petrol/diesel/lpg/electric/hybrid — Бензин/Дизель/ГБО/Електро/Гібрид), Поточний пробіг (`current_odometer`). Картка кожного авто: назва, рік · двигун · пальне, пробіг + «≈ N км/день» (`avg_daily_km`), бейдж «Активне» (синя рамка-ring); кнопки «Зробити активним», завантаження PDF-звіту, редагування (олівець → та сама CarForm), видалення (`window.confirm` з попередженням «Разом з авто буде видалено весь журнал»).
- **Інтервали ТО активного авто**: список (назва з кольором статусу; «кожні N км» / «кожні N дн.»; «Останнє: <км> · <дата>»), кнопка «Додати» відкриває інлайн-форму `IntervalForm` (Назва `title`, Інтервал км `interval_km`, Інтервал дні `interval_days` — потрібен хоча б один; Останнє ТО км `last_odometer`, Дата останнього ТО `last_date`). Кнопка «Створити типові інтервали» створює 6 пресетів послідовними POST-ами: Олива двигуна (10 000 км / 365 дн.), Повітряний фільтр (20 000 км), Паливний фільтр (30 000 км), Салонний фільтр (15 000 км / 365 дн.), ГРМ (120 000 км), Гальмівна рідина (60 000 км / 730 дн.) — усі з `last_odometer = current_odometer` і `last_date = сьогодні`.
- **Дії над інтервалом — тільки видалення** (`window.confirm`). **Редагування інтервалу відсутнє** (функція `updateInterval(intervalId, payload)` → `PATCH /api/intervals/:id` є в `api/intervals.js`, але UI її не використовує). Немає й способу «відмітити виконаним» — після фактичного ТО користувач мусить видалити і створити інтервал заново, або чекати на бекенд-логіку.
- **TelegramCard**: показує статус привʼязки (`GET /api/telegram/status` → `{linked}`); кнопка «Привʼязати Telegram» → `POST /api/telegram/link-code` → показ коду (з кнопкою копіювання в буфер) + кнопка «Відкрити бота» (`deep_link`, `window.open`) + інструкція «Надішліть боту /start <код>. Код діє N хвилин» (`expires_in_minutes`); «Відвʼязати» → `window.confirm` → `DELETE /api/telegram/link`.

## 4.2. Стейт-менеджмент (zustand)

Два стори без middleware (persist не використовується — персистенція ручна через `localStorage`):

**`store/authStore.js`** — `token` (ініціалізується з `localStorage['kapot_tracker_token']`), `user`, `userLoading`. Дії: `login(email, password)` (`POST /api/auth/token`, OAuth2 form-urlencoded, зберігає токен, потім `GET /api/auth/me`), `register` (POST `/api/auth/register` + одразу login), `fetchMe`, `logout` (чистить токен і user).

**`store/carStore.js`** — центральний кеш даних:
- Стан: `cars[]`, `activeCarId` (ініціалізується з `localStorage['kapot_tracker_active_car']`), `logs {items, total}`, `intervals[]`, `analytics` — кожен ресурс зі своєю парою `*Loading` / `*Error` (тексти помилок українською зашиті в стор) + прапорець `carsLoaded`.
- `fetchCars()` — валідує збережений `activeCarId` проти отриманого списку; якщо авто зникло, активним стає перше авто (або null), localStorage синхронізується.
- `setActiveCar(id)` — пише в localStorage і **скидає всі кеші залежних даних** (logs, intervals, analytics) — наступний екран перезавантажить їх для нового авто.
- Мутації самі рефетчать залежності: `addLog` → паралельно `fetchCars()` + `fetchLogs()` (бо створення запису може підняти `car.current_odometer` на бекенді); `removeLog` → `fetchLogs` зі збереженням поточного фільтра; `addCar/editCar/removeCar` → `fetchCars`; `addInterval/removeInterval/addIntervalPresets` → `fetchIntervals`.
- `reset()` — викликається при логауті, чистить усе і видаляє ключ активного авто.
- Кешування «наївне»: дані живуть у памʼяті стора, але кожен екран у `useEffect` рефетчить свій ресурс при монтуванні/зміні `activeCarId`; TTL, SWR-патернів чи React Query немає.

**HTTP-шар** (`api/client.js`): axios-інстанс з `baseURL: '/api'`; request-інтерцептор додає `Authorization: Bearer <token>` з localStorage; response-інтерцептор на **401** видаляє токен і робить жорсткий redirect `window.location.href = '/login'` (втрачається стан SPA). `extractError(error, fallback)` дістає `detail` з відповіді FastAPI (рядок або масив валідаційних помилок).

## 4.3. PWA-конфігурація

- **vite-plugin-pwa** (`vite.config.js`): `registerType: 'autoUpdate'` — сервіс-воркер оновлюється автоматично без промпта; у `main.jsx` — `registerSW({ immediate: true })`.
- **Маніфест**: `name: "Kapot Tracker"`, `short_name: "Kapot"`, `description: "Журнал обслуговування та витрат вашого авто"`, `theme_color` і `background_color` — `#0f172a` (slate-900), `display: "standalone"`. Іконка **одна — SVG** (`/icon.svg`, `sizes: "any"`): синє авто на темному закругленому квадраті; PNG-іконок немає (потенційна проблема для iOS, де `apple-touch-icon` вказує на той самий SVG, який Safari не підтримує повноцінно).
- **Dev-проксі**: `server.proxy['/api'] → http://localhost:8000` (FastAPI), `changeOrigin: true`.
- **Прод (nginx.conf у Docker-образі)**: SPA-fallback `try_files … /index.html`; `location /api/` проксіює на `http://backend:8000` зі збереженням префікса `/api`; `client_max_body_size 12m` (фото чеків для OCR до 10 МБ); `sw.js` і `manifest.webmanifest` віддаються з `Cache-Control: no-cache`; gzip для текстових типів.
- **Офлайн**: workbox прекешує лише статичні асети збірки; API-запити не кешуються — **без мережі застосунок не показує даних** (офлайн-режим фактично відсутній).

## 4.4. Дизайн-система (описово)

- **Тільки темна тема** на палітрі Tailwind slate: фон сторінки `slate-950`, картки `slate-900` з рамкою `slate-800`, інпути `slate-800` з рамкою `slate-700`, основний текст `slate-100`, вторинний `slate-400/500`. Акцент — `blue-600` (кнопки, активна навігація, прогрес-бари), попередження — `amber`, небезпека — `red`, успіх — `emerald`. Світлої теми і перемикача немає; `tailwind.config.js` без розширень теми.
- **Мобільна колонка**: увесь контент обмежено `max-w-md` (448 px) по центру — застосунок є mobile-first, на десктопі виглядає як вузька стрічка. Радіуси щедрі (`rounded-xl` / `rounded-2xl`), шрифт системний (`system-ui, -apple-system, 'Segoe UI'`).
- **Нижня навігація з 5 пунктів** з центральною круглою FAB «Додати» — головний патерн навігації.
- **Числа/дати** (`utils/format.js`): гроші «1 250,50 ₴» з вузьким нерозривним пробілом як роздільником тисяч і комою в дробовій частині (`,00` ховається); кілометри «123 456 км»; дати `dd.mm.yyyy`; місяці — українські скорочення («лип 2026»). Спінери в number-інпутах приховані CSS.
- **Графіки** — Recharts на темній поверхні: сітка `#1e293b`, осі/підписи `#64748b`, кастомний тултіп у стилі карток, категоріальна палітра 4 типів витрат (див. 4.1/Analytics), однакові кольори повторно використані у бейджах журналу (`LOG_TYPE_META`).

## 4.5. UI-примітиви

Наявні (`components/UI/`, реекспорт через `index.js`):
- **Button** — 4 варіанти: `primary` (синій), `secondary` (сірий з рамкою), `danger` (напівпрозорий червоний), `ghost`; `type="button"` за замовчуванням.
- **Input** — з опційними `label` і `hint`, автогенерація `id` з label.
- **Select** — стилізований нативний select з масивом `options`.
- **Card** — `rounded-2xl border-slate-800 bg-slate-900 p-4`.
- **Toggle** — кастомний перемикач `role="switch"` + `aria-checked`.
- **Spinner** — обертовий Loader2 з `aria-label`.
- **ErrorMessage** — червоний алерт-блок `role="alert"` з іконкою (рендерить null без children).
- **Toast** (`components/Toast.jsx`) — зелене повідомлення успіху, fixed зверху по центру, автоприховування через 3000 мс, без черги і без варіантів error/warning.

**Відсутні (заплановані в ітерації «повного редагування»)**: **Modal**, **ConfirmDialog** — усі підтвердження зараз через нативний `window.confirm`, помилки видалення — через `window.alert`; форми відкриваються інлайн у потоці сторінки, а не в модалці. Також немає Skeleton-лоадерів, компонента пагінації, DatePicker (нативний `type="date"`), Combobox/Autocomplete.

## 4.6. Відомі UX-обмеження

1. **Нативні `window.confirm` / `window.alert`** для всіх деструктивних дій (видалення запису, авто, інтервалу, відвʼязка Telegram) — не стилізовані, англомовні кнопки ОК/Cancel, блокують потік.
2. **Немає перегляду і редагування запису журналу** — помилку в збереженому записі можна виправити лише видаленням і повторним створенням; API-функції `updateLog` (PATCH `/api/logs/:id`) і `updateInterval` (PATCH `/api/intervals/:id`) уже написані у фронтенд-API-шарі, але не мають UI.
3. **Немає редагування інтервалів ТО** і кнопки «виконано» — тільки створення/видалення.
4. **Dark-only** — світлої теми немає, `prefers-color-scheme` ігнорується.
5. **Немає офлайн-режиму** — PWA кешує тільки статику; без мережі жодних даних.
6. **Пагінація журналу декоративна** — перші 50 записів + напис «Показано X з Y», без завантаження наступних сторінок; пошуку по журналу немає.
7. Жорсткий redirect `window.location.href='/login'` на 401 губить стан SPA і незбережені форми.
8. `carStore.addIntervalPresets` створює 6 інтервалів **послідовними** POST-ами без транзакції — обрив на середині лишає частковий набір.
9. Toast лише одного типу (успіх), без черги; повідомлення про успіх додавання передається через `location.state`, тож оновлення сторінки на `/logbook` його не відтворить (це радше плюс, але механізм крихкий).
10. PWA-іконка тільки SVG — на iOS домашній екран може отримати неякісну/порожню іконку.
11. Немає віджета швидкого оновлення пробігу, дублювання записів і фото-вкладень до записів — усе це у спроєктованій, але нереалізованій ітерації «повного редагування» (сторінка `/logbook/:id`, редагування інтервалів, пошук, віджет одометра).

---

## 5. Інфраструктура, якість, відомі обмеження

## 5.1 Запуск проєкту

### Локальна розробка (без Docker)

Два процеси, які зручно стартувати одним скриптом `scripts/dev.sh` (перевіряє наявність `backend/.venv` і `frontend/node_modules`, запускає обидва процеси і коректно вбиває їх по Ctrl+C):

| Компонент | Команда | Порт / URL |
|---|---|---|
| Backend | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` | http://localhost:8000 (Swagger: `/docs`) |
| Frontend | `cd frontend && npm run dev` (Vite dev server) | http://localhost:5173 |
| Telegram-бот | `python -m app.bot.main` (у venv backend-а) | polling, порту немає |

- За замовчуванням backend працює на **SQLite** — файл `backend/kapot_tracker.db` створюється автоматично, окрема БД не потрібна.
- Для OCR локально потрібен системний бінарник tesseract (`brew install tesseract tesseract-lang` на macOS). Якщо бінарника немає — `POST /api/ocr/scan` відповідає `503`, решта API працює.
- Бот при порожньому `TELEGRAM_BOT_TOKEN` одразу завершується з кодом 0 (свідома поведінка, щоб не падати).
- Vite dev server проксіює запити до API; у продакшен-режимі цю роль виконує nginx (нижче).

### Docker (docker-compose)

```
cp .env.example .env   # обов'язково змінити SECRET_KEY
docker compose up --build          # db + backend + frontend
docker compose --profile bot up    # те саме + Telegram-бот
```

Топологія сервісів у `docker-compose.yml`:

| Сервіс | Образ / збірка | Порти (host:container) | Примітки |
|---|---|---|---|
| `db` | `postgres:16-alpine` | **не публікується назовні** (лише внутрішня мережа, 5432) | volume `pgdata`, healthcheck `pg_isready` (5s × 10 retries) |
| `backend` | `./backend` (python:3.12-slim + tesseract-ocr + tesseract-ocr-ukr + tesseract-ocr-eng), uvicorn | `8000:8000` | стартує лише після healthy db |
| `bot` | той самий образ, що backend, але `command: python -m app.bot.main` | немає | **профіль `["bot"]`** — не стартує при звичайному `up`, лише з `--profile bot`; `restart: unless-stopped` |
| `frontend` | multi-stage: `node:20-alpine` (npm ci + vite build) → `nginx:alpine` | `3000:80` | статика + reverse proxy |

nginx-конфіг фронтенда (`frontend/nginx.conf`):
- SPA fallback: `try_files $uri $uri/ /index.html`;
- `location /api/` → `proxy_pass http://backend:8000` (префікс `/api` зберігається), прокидаються `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`;
- `client_max_body_size 12m` — щоб фото чеків до 10 МБ для `/api/ocr/scan` проходили (дефолт nginx — 1m);
- `Cache-Control: no-cache` для `/sw.js` і `/manifest.webmanifest` (щоб PWA-оновлення не «залипали» в кеші);
- gzip для text/css/js/json/svg.

У Docker `DATABASE_URL` для backend і bot жорстко зібраний у compose: `postgresql+psycopg2://<POSTGRES_USER>:<POSTGRES_PASSWORD>@db:5432/<POSTGRES_DB>` — тобто в контейнерах завжди PostgreSQL, а локально без Docker — SQLite. Це джерело розбіжності dev/prod (див. 5.5).

## 5.2 CI (GitHub Actions)

Один workflow `.github/workflows/ci.yml` (name: `CI`), тригери — **кожен `push` і `pull_request`** (без фільтрів по гілках). Два незалежні jobs на `ubuntu-latest`:

1. **backend**: checkout → setup-python **3.12** (pip-кеш по `backend/requirements.txt`) → `pip install -r backend/requirements.txt` → `pytest` у `backend/`.
2. **frontend**: checkout → setup-node **20** (npm-кеш по `frontend/package-lock.json`) → `npm ci` → `npm run build` → `npm run test --if-present` (vitest).

Чого в CI **немає**: лінтерів (eslint/ruff), type-check, збірки docker-образів, звіту покриття (coverage), e2e-тестів, деплою. CI — це «тести + фронтенд-білд», не більше.

## 5.3 Тестове покриття

Фактичні цифри (перевірено запуском 2026-07-14): **backend — 147 тестів, усі зелені** (`pytest`, ~34 с); **frontend — 34 тести у 3 файлах, усі зелені** (`vitest`, <1 с).

Розподіл backend-тестів по файлах (`backend/tests/`):

| Файл | Тестів | Що покрито |
|---|---|---|
| `test_ocr.py` | 35 | Парсер тексту чеків: сума, літри, ціна/л, дата, «ремонт» літрів із рядків виду `X.XX x ЦІНА`, поведінка без tesseract (503) |
| `test_bot_parsers.py` | 29 | Парсери повідомлень бота: число → пробіг, `мийка 300` → швидка витрата, крайові випадки |
| `test_forecast.py` | 12 | Прогнозна аналітика: середні витрати/міс, прогноз поточного місяця, найближчі ТО з орієнтовною вартістю |
| `test_intervals.py` | 11 | CRUD сервісних інтервалів, розрахунок прогнозу наступного ТО |
| `test_telegram.py` | 11 | Привʼязка акаунта: генерація коду, TTL, статус, відвʼязка |
| `test_logs.py` | 10 | CRUD записів журналу, включно з **ownership** (чужі car_id/log_id → 404) |
| `test_auth.py` | 8 | Реєстрація, вхід, JWT, `/api/auth/me` |
| `test_cars.py` | 6 | CRUD авто + ownership |
| `test_reminders.py` | 6 | Нагадування бота про наближення ТО (`last_notified_at`) |
| `test_bot_service.py` | 5 | Сервісний шар бота (`/status`, запис у БД) |
| `test_analytics.py` | 4 | Агрегації аналітики |
| `test_fuel_math.py` | 4 | Математика розходу «повний-до-повного» |
| `test_report.py` | 4 | PDF-звіт (генерується, містить кирилицю/дані) |
| `test_migrations.py` | 2 | `ensure_schema()` — додавання відсутніх колонок |

Frontend-тести — **лише чисті функції, жодного компонента**: `src/utils/refuelMath.test.js` (17 — розхід пального), `src/utils/format.test.js` (14 — форматування), `src/api/reports.test.js` (3 — клієнт звітів). React-компоненти, роутинг, стори (zustand), PWA-поведінка — не покриті взагалі; e2e-тестів немає.

Чесне спостереження щодо стабільності: під час перевірки один із запусків повного backend-набору показав 2 падіння у `tests/test_ocr.py` (`test_price_from_x_line_when_liters_marker_also_present`, `test_liters_repaired_when_product_with_price_not_in_text`), які не відтворилися в жодному з наступних запусків (3× повний набір, 3× тільки OCR — усе зелене). Ймовірний одиничний флейк середовища, але варто мати на увазі. Також локальний venv працює на **Python 3.14**, тоді як CI та Docker — на **3.12** (розбіжність версій; у 3.14 вилазить deprecation-warning starlette testclient).

## 5.4 Змінні середовища

Джерело — `.env.example` (копіюється в `.env`); docker-compose має власні дефолти-fallback (`${VAR:-default}`).

| Змінна | Призначення | Дефолт локально / у compose |
|---|---|---|
| `SECRET_KEY` | Ключ підпису JWT | `change-me-to-a-long-random-string` / fallback у compose — **`change-me-in-production`** (небезпечний дефолт) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Термін дії access-токена, хв | `60` |
| `DATABASE_URL` | SQLAlchemy URL БД | `sqlite:///./kapot_tracker.db`; у compose перевизначається на `postgresql+psycopg2://...@db:5432/...` |
| `CORS_ORIGINS` | Дозволені origin-и через кому | `http://localhost:5173,http://localhost:3000` |
| `TELEGRAM_BOT_TOKEN` | Токен від @BotFather; порожній → бот завершується (exit 0) | порожній |
| `TELEGRAM_BOT_USERNAME` | Username бота без `@` (deep-link кнопка в «Гаражі») | порожній |
| `LINK_CODE_EXPIRE_MINUTES` | TTL коду привʼязки Telegram, хв | `15` |
| `POSTGRES_USER` | Користувач PostgreSQL (Docker) | `kapot_tracker` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL (Docker) | `kapot_tracker` (дефолт = логін, слабко) |
| `POSTGRES_DB` | Назва БД PostgreSQL (Docker) | `kapot_tracker_db` |

## 5.5 Відомі обмеження і технічний борг (відвертий список)

Це чесний перелік для зовнішнього аудиту — без прикрас, у приблизному порядку болючості:

1. **Немає жодних бекапів — і вже був реальний інцидент.** При перейменуванні проєкту з CarKeeper на Kapot Tracker (2026-07-14) dev-базу з реальною сервісною історією VW Golf було втрачено (перейменування зачепило імена файлу SQLite та ідентифікатори БД/volume), дані довелося відновлювати повторним сідінгом. Немає ні pg_dump-крону, ні snapshot-ів volume `pgdata`, ні копіювання SQLite-файлу. Для продукту, чия головна цінність — багаторічна історія авто, це обмеження №1.
2. **Немає міграцій (Alembic відсутній).** Схема створюється через `Base.metadata.create_all()` + самописний `app/migrations.py::ensure_schema()`, який уміє лише **додавати колонки** з хардкод-списку `EXPECTED_COLUMNS` (зараз дві: `users.telegram_chat_id VARCHAR(50)`, `service_intervals.last_notified_at DATE`) простим `ALTER TABLE ... ADD COLUMN`. Перейменування, видалення, зміна типу, backfill даних — неможливі. Кожна нова колонка вимагає ручного допису в цей список; ризик дрейфу схеми між SQLite (dev) і PostgreSQL (prod) зростає з кожною зміною.
3. **Немає відновлення пароля.** Ендпоінта типу `/forgot-password` не існує; забутий пароль = назавжди втрачений акаунт разом з усією історією авто. Email нікуди не надсилається взагалі (SMTP-інтеграції немає).
4. **Немає email-верифікації.** Реєстрація приймає будь-який рядок-email без підтвердження; можна зареєструватися на чужу адресу.
5. **JWT зберігається в localStorage** (`frontend/src/api/client.js`, ключ `TOKEN_KEY`). Будь-який XSS = крадіжка токена. Немає refresh-токенів: після 60 хв (дефолт `ACCESS_TOKEN_EXPIRE_MINUTES`) користувача просто розлогінює (клієнт на 401 видаляє токен). httpOnly-cookie не використовуються.
6. **Немає rate-limiting ніде.** `/api/auth/token` можна брутфорсити без обмежень; `/api/ocr/scan` (дорогий tesseract + фото до 10 МБ) можна заспамити; генерацію кодів привʼязки Telegram — теж. Жодного middleware, жодного captcha.
7. **SQLite за замовчуванням локально, PostgreSQL — лише в Docker.** Розбіжність dev/prod: різні діалекти, різна поведінка NUMERIC/дат, один письменник у SQLite. Баги, специфічні для PostgreSQL, локально не відтворюються (і навпаки).
8. **PWA-іконка — лише SVG** (`frontend/public/icon.svg`, єдиний файл у `public/`; manifest посилається тільки на нього). **iOS не підтримує SVG** для іконок домашнього екрана (apple-touch-icon має бути PNG), maskable PNG 192×192/512×512 відсутні — на iPhone застосунок встановлюється з «порожньою»/згенерованою іконкою. Для мобільного продукту це помітний недолік.
9. **Немає офлайн-черги.** Service worker кешує лише статику: застосунок офлайн відкривається, але будь-який запис (POST/PUT/DELETE) без мережі просто падає — дані з заправки «в полі» без покриття втрачаються. IndexedDB-черга синхронізації — лише ідея Етапу 4.
10. **Митні витрати в EUR не конвертуються.** Модель `log_entries` має єдине поле `total_cost NUMERIC(10,2)` без валюти. У реальній seed-історії запис «Митне оформлення експорту в Україну» (2022-10-19, інвойс у EUR) збережений з `total_cost = 0` — тобто задокументовані 87 323 грн **занижують** фактичну вартість володіння авто. Мультивалютності немає (ідея Етапу 4).
11. **Слабкі дефолти секретів.** `docker-compose.yml` має fallback `SECRET_KEY=change-me-in-production` і `POSTGRES_PASSWORD=kapot_tracker` — якщо `.env` не заповнити, стек «просто працює» з передбачуваними секретами, без жодного попередження на старті.
12. **CI мінімальний**: немає лінтерів, type-check, coverage-звіту, збірки docker-образів, e2e; frontend-тести покривають лише утиліти (34 тести, нуль компонентних). Версія Python у локальному venv (3.14) не збігається з CI/Docker (3.12).
13. **Немає TLS/HTTPS** у compose-стеку (nginx слухає голий 80; термінацію TLS треба вішати зовні самостійно) і немає жодного моніторингу/логування помилок (Sentry тощо) — про падіння в проді дізнатися нізвідки.
14. **Одиночний процес бота на long polling** без захисту від подвійного запуску: два екземпляри з одним токеном конфліктуватимуть на getUpdates.

Окремо нагадування з контексту продукту: ітерація «повне редагування» (сторінка запису `/logbook/:id` з редагуванням, редагування інтервалів, фото-вкладення, пошук по журналу, швидкий віджет пробігу, дублювання записів) — **спроєктована, але не реалізована**; наразі записи й інтервали можна лише створювати та видаляти, що для щоденного журналу є відчутним функціональним боргом.

---

## 6. Куди продукт рухається

### Затверджена ітерація «Повний контроль» (в розробці)
Детальна сторінка запису журналу `/logbook/:id` (повні нотатки, список робіт, гарантія) з режимом редагування; редагування сервісних інтервалів; фото-вкладення до записів (локальний диск, до 10 МБ, OCR-скан зберігається автоматично); пошук по журналу (нотатки, роботи, деталі, АЗС); швидке оновлення пробігу з дашборда; дублювання запису; UI-примітиви Modal/ConfirmDialog замість window.confirm.

### Наступні ітерації (за пріоритезованим беклогом із 61 пропозиції)
1. **«Дані в безпеці»** — автоматичний бекап + копія в Telegram, JSON/CSV експорт-імпорт (з мапінгом Fuelio/Drivvo), скидання пароля через привʼязаний Telegram, rate-limiting логіна. Мета: жодна одинична подія не знищить історію (інцидент втрати dev-бази вже був).
2. **«Щоденна заправка»** — чіпси улюблених АЗС і підстановка минулої ціни, санітарні попередження дата/пробіг, багаторядкові нотатки, л/100км у рядку заправки, категорії витрат, фікс десяткової коми.
3. **«Бот і сервіс без тертя»** — «Виконано» одним тапом (створює запис ТО і зсуває інтервал транзакційно), дата-інтервали для ОСЦПВ/техогляду/зеленої карти, заправка текстом і фото через бота, inline-кнопки в нагадуваннях.
4. **«Справжня PWA»** — повноцінний набір іконок (iOS!), офлайн-індикатор і черга записів (IndexedDB), NetworkFirst-кеш.

### Відкриті питання для роздумів
1. **Монетизація vs один користувач:** freemium-план зі спеки має сенс лише за наявності аудиторії. Що є мінімальним «продуктовим доказом», після якого варто вмикати білінг — і чи не вбʼє paywall головну цінність (повна історія авто)?
2. **OCR-стеля:** tesseract добре читає касові чеки АЗС, але рукописні наряди СТО і багатосторінкові інвойси — ні. Коли виправдано підключити LLM-vision API (вартість, приватність фінансових документів) і чи робити його опційним «преміум»-парсером?
3. **Бекапи без болю:** яка схема реально виживе для self-hosted користувача — щоденний дамп у Telegram-чат самому собі, S3-люстро, чи git-подібний журнал змін? Що з шифруванням?
4. **fuel_type на кожну заправку:** міграцію дешевше зробити зараз, поки заправок у базі нуль. Але чи виправдана складність UI для водіїв без ГБО? Як спроєктувати, щоб бензинова машина її не помічала?
5. **Токен у localStorage vs httpOnly cookie:** PWA-простота проти XSS-стійкості. Який компроміс правильний для додатка з фінансовими даними одного користувача?
6. **Скрейпінг цін на пальне по Україні:** фіча-вау для порівняння АЗС чи баласт на підтримку? Джерела нестабільні, аудиторія — одна людина.
7. **Спільний доступ:** сімʼя з двома водіями одного авто — це вже «мультиюзер на машину». Наскільки глибоко це міняє модель даних (власник vs водій), і чи варто закладати зараз?

