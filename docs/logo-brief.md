# Kapot Tracker — бриф на логотип

Мета: замінити застарілу іконку (синє авто `#2563eb` на слейті `#0f172a` — з часів
до редизайну) на знак, що відповідає бурштиново-гаражній дизайн-системі й обіграє
саму назву.

## Що таке продукт (контекст для генератора)

Український бортовий журнал авто: сфотографував чек з АЗС → застосунок розпізнав
літри/ціну/суму, порахував розхід, стежить за ТО, нагадує в Telegram. Аудиторія —
власники вживаних авто, часто пригнаних з ЄС. Голос: «Сфоткай чек. Решту запише сам».

**Назва.** «Kapot» (капот) = hood/bonnet авто. «Kapot Tracker» = стежити за тим, що
**під капотом**. Це головний, нічим не зайнятий візуальний гачок — конкуренти
(Drivvo, Fuelio) усі беруть generic авто чи краплю пального.

## ДНК (звідки береться візуальна мова)

- **Нічний гараж** — майже чорне синьо-чорне тло `#0B1119`.
- **Бурштин `#FFB454`** — ЄДИНИЙ яскравий колір. Це саме бурштин **приладової
  панелі** / лампи «check engine». Глибший відтінок `#E8912B` — для об'єму.
- **Фіскальний чек / термопапір** `#F2EEE3` + моноширинні цифри — ядро продукту (OCR).
- **Синій — заборонено** у брендингу (зарезервований лише за Telegram).
- Шрифт-дисплей **Unbounded** (жирний, геометричний, округлий). Ворордмарк:
  «KAPOT» світлим + «TRACKER» бурштином, великими літерами.

## Фіксовані обмеження (незмінні для будь-якого концепту)

- Квадратна **іконка застосунку**: знак у центрі, темне тло `#0B1119`,
  щедрі поля (safe-zone під маску Android).
- Один акцент — **бурштин `#FFB454`** (з легким світінням), опційно `#E8912B` для
  глибини. Жодного синього чи інших кольорів.
- **Плаский вектор**, геометрія, товсті округлі штрихи в дусі Unbounded. Мінімалізм,
  високий контраст, читабельність на 32px. **Без тексту** (крім концепту-монограми).
- Настрій: нічний гараж + тепле світіння приладової лампи.

---

## Концепти (готові промпти, English — генератори працюють краще)

Спільний «хвіст стилю» (додається до кожного):

> flat vector app icon, minimal geometric logo, single glowing amber #FFB454 mark on a
> near-black night-garage #0B1119 rounded-square background, thick rounded strokes, bold
> and modern like the Unbounded typeface, high contrast, centered with generous padding,
> crisp and legible at small sizes, subtle warm amber glow, no text, no photorealism,
> no 3D, no gloss, no heavy gradients, no blue

### D — ГЕРОЙ: капот + лампа під ним (синтез назви й «панелі здоров'я»)
> A minimalist emblem of a car hood, slightly raised/open, seen from a three-quarter
> front angle, with a soft amber warning-lamp glow emanating from underneath it,
> symbolising monitoring what's under the hood — [хвіст стилю]

### A — чистий капот (буквальна назва)
> A bold geometric emblem of a car hood/bonnet in side profile, one confident amber line
> forming the curved hood silhouette — [хвіст стилю]

### B — приладова лампа / манометр (панель здоров'я)
> A minimal dashboard gauge: a semicircular amber arc with a single needle pointing
> up-right, evoking an odometer and a warm amber warning lamp — [хвіст стилю]

### C — монограма «К» (кирилиця, масштабується у фавікон)
> A bold monogram of the Cyrillic letter К (Ka) in a chunky rounded geometric style
> matching the Unbounded typeface, amber, the diagonal stroke subtly shaped like a car
> hood line or a gauge needle, on a near-black #0B1119 rounded-square, flat vector,
> high contrast, legible at small sizes, subtle amber glow, no other text, no blue

### E — фіскальний чек (другорядний; читається радше як «фінанси», не «авто»)
> A minimal fuel-receipt icon with a zigzag torn bottom edge and a single amber scan
> line crossing it — [хвіст стилю]

---

## Negative prompt (якщо генератор його підтримує)
> text, letters, words, watermark, photorealistic, realistic car photo, 3D render, glossy,
> bevel, heavy gradient, drop shadow clutter, blue, teal, rainbow, stock car silhouette,
> clip art, busy background

## Поради
- Формат `--ar 1:1`, згенеруй 6–8 варіантів, вибери 1.
- Тестуй у зменшенні: якщо на 32px перетворюється на пляму — надто складно.
- Веди з **D** або **A** (капот) — це найвласніше; **C** — найбезпечніше й ідеально
  ляже у фавікон.
- Растровий результат — це референс. Далі його треба перемалювати в чистий **SVG**
  (застосунку потрібні `icon.svg` + PNG 192/512/maskable/apple-touch + фавікон).
