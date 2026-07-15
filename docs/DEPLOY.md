# Деплой Kapot Tracker — Oracle Free Tier + DuckDNS + Caddy

Повністю безкоштовний публічний хостинг: ARM-інстанс Oracle (безкоштовно **назавжди**, не тріал), безкоштовний піддомен DuckDNS і Caddy, який сам візьме сертифікат Let's Encrypt.

**Що отримаємо:** `https://kapot.duckdns.org` — справжній HTTPS (отже, PWA встановлюється на телефон і працює офлайн-черга), 24/7 (нагадування і бекапи йдуть, навіть коли ноут закритий).

---

## 0. Перед початком

Знадобиться: акаунт Oracle Cloud (реєстрація вимагає картку **для верифікації, без списання**), 20–30 хвилин.

⚠️ **Обовʼязково обери регіон, де є ARM-потужності** (Frankfurt і Amsterdam часто «Out of capacity»). Якщо при створенні інстансу бачиш `Out of host capacity` — спробуй пізніше або інший AD (availability domain). Це найчастіший затик, і він не про твої налаштування.

---

## 1. Інстанс Oracle

1. Create Instance → Image: **Ubuntu 22.04** → Shape: **VM.Standard.A1.Flex** (Ampere ARM).
2. Ресурси: **2 OCPU / 12 GB RAM** — половина безкоштовного ліміту (4/24), лишиш запас на другий інстанс. Нашому стеку цього з надлишком.
3. Додай свій SSH-ключ (або згенеруй: `ssh-keygen -t ed25519`).
4. **Networking → відкрий порти 80 і 443:**
   - VCN → Security Lists → Default → Add Ingress Rules:
     - Source `0.0.0.0/0`, TCP, Destination Port `80`
     - Source `0.0.0.0/0`, TCP, Destination Port `443`
   - ⚠️ Цього **недостатньо**: Ubuntu на Oracle має власний iptables, який блокує все, крім 22. На інстансі:
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save
     ```
     Забути це — класична причина «Caddy не може отримати сертифікат».

## 2. DuckDNS

1. https://www.duckdns.org → увійти через GitHub/Google.
2. Створити субдомен, напр. `kapot` → отримаєш `kapot.duckdns.org` і токен.
3. Вписати **публічний IP інстансу** в поле `current ip` → Update.
4. Перевірити з ноута: `dig +short kapot.duckdns.org` має віддати той самий IP.

## 3. Docker на інстансі

```bash
ssh ubuntu@<IP>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit   # перезайти, щоб група підхопилась
```

## 4. Код і конфіг

```bash
ssh ubuntu@<IP>
git clone https://github.com/KonG196/CarTrack.git kapot && cd kapot
cp .env.example .env
nano .env
```

Заповнити в `.env`:

```ini
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
POSTGRES_PASSWORD=<довгий випадковий>
DATABASE_URL=postgresql+psycopg2://kapot_tracker:<той самий пароль>@db:5432/kapot_tracker_db

# Публічний домен — інакше CORS заблокує фронтенд, а листи вестимуть на localhost
CORS_ORIGINS=https://kapot.duckdns.org
PUBLIC_URL=https://kapot.duckdns.org

TELEGRAM_BOT_TOKEN=<від @BotFather>
TELEGRAM_BOT_USERNAME=Kapot_Tracker_bot
BACKUP_TELEGRAM_CHAT_ID=<твій chat_id, див. §7>

# Пошта — без неї реєстрація авто-підтверджується (для публічного хосту це діра)
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<логін Brevo>
SMTP_PASSWORD=<SMTP-ключ Brevo>
SMTP_FROM=Kapot Tracker <maks060691@gmail.com>
```

**Пошта:** [Brevo](https://www.brevo.com) — безкоштовно 300 листів/добу, дозволяє відправку з підтвердженої Gmail-адреси (домен не потрібен). Альтернатива — Gmail SMTP з app password (`smtp.gmail.com:587`), але Google частіше ріже такі відправки.

## 5. Запуск

```bash
docker compose up -d --build          # API + фронт + Postgres
docker compose --profile bot up -d    # Telegram-бот
docker compose logs -f backend        # переконатись, що міграції накотились
```

Міграції Alembic виконуються автоматично на старті (`run_migrations` у lifespan) — руками нічого запускати не треба.

## 6. Caddy (HTTPS)

Caddy ставимо **на хост**, не в compose: він слухає 80/443 і проксює на фронтенд-контейнер (3000).

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
sudo nano /etc/caddy/Caddyfile
```

Уся конфігурація — три рядки:

```caddyfile
kapot.duckdns.org {
    reverse_proxy localhost:3000
}
```

```bash
sudo systemctl reload caddy
sudo journalctl -u caddy -f     # має зʼявитись "certificate obtained successfully"
```

Відкрити https://kapot.duckdns.org — має бути замочок і застосунок.

## 7. Бекапи в Telegram

1. Написати боту будь-що.
2. `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` → знайти `"chat":{"id":<число>}`.
3. Вписати це число в `.env` як `BACKUP_TELEGRAM_CHAT_ID`, перезапустити бота:
   `docker compose --profile bot up -d --force-recreate`
4. Перевірити вручну: `docker compose exec backend python -m app.backup` — дамп має прилетіти в чат.

⚠️ Бекап містить дані **всіх** користувачів, тому летить лише в цей адмінський чат і нікуди більше.

## 8. Перевірка після деплою

- [ ] `https://kapot.duckdns.org` відкривається з HTTPS
- [ ] Реєстрація нового акаунта → **лист із кодом приходить** (якщо ні — дивись `docker compose logs backend | grep SMTP`)
- [ ] Вхід без підтвердження → 403 з підказкою
- [ ] На телефоні: Safari/Chrome → «Додати на екран Додому» → додаток встановлюється з іконкою
- [ ] Увімкнути режим польоту, додати заправку → «Очікує синхронізації» → повернути мережу → запис синхронізувався
- [ ] Бот відповідає на `/status`
- [ ] `docker compose exec backend python -m app.backup` → файл у чаті

## 9. Міграція даних з ноута

Якщо в локальній базі вже є твоя історія Гольфа:

```bash
# на ноуті
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/export > kapot-export.json
# зареєструватись на новому хості, підтвердити пошту, взяти новий токен
curl -X POST https://kapot.duckdns.org/api/import \
  -H "Authorization: Bearer <новий token>" \
  -H "Content-Type: application/json" \
  --data-binary @kapot-export.json
```

⚠️ Експорт містить **лише метадані фото**, самі файли не переносяться (обмеження формату). Фото чеків доведеться перезавантажити вручну або скопіювати теку `uploads/` через `scp` + `docker cp`.

## 10. Оновлення

```bash
cd kapot && git pull
docker compose up -d --build
docker compose --profile bot up -d --build
```

Міграції накотяться самі. Перед оновленням зі зміною схеми — зроби бекап (`python -m app.backup`).

---

## Відомі обмеження цієї схеми

- **Один інстанс, без реплікації.** Бекап щоденний → втрата до доби між дампами.
- **Oracle може відібрати «неактивні» free-інстанси** — політика Always Free це формально дозволяє при простої CPU. Наш стек постійно щось робить (бот полить Telegram), тож ризик малий, але бекап у Telegram — твоя страховка.
- **DuckDNS — сторонній сервіс.** Ляже він — ляже і домен. Для серйозного продакшену краще свій домен (~$10/рік) на Cloudflare.
- **Немає моніторингу.** Мінімум: підключити безкоштовний UptimeRobot на `https://kapot.duckdns.org/api/health` — пуш прилетить, якщо ляже.
