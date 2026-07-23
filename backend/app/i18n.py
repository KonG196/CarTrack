"""Backend localization: per-user language + a small message catalog.

The language a user picks in the app (stored on ``User.language``) also decides
the language of the emails, Telegram messages and API error details they get.
English is the default; Ukrainian is the second language.

Usage:
    from app.i18n import t, normalize_lang
    raise HTTPException(400, detail=t("auth.email_taken", user.language))
    t("bot.reminder_due", lang, title=interval.title, km=1200)

Templates use ``str.format(**kwargs)`` — keep placeholders identical across
languages. A missing key or language falls back to English, then to the key
itself, so a gap degrades to something readable rather than crashing.
"""

from __future__ import annotations

from typing import Optional

SUPPORTED: tuple[str, ...] = ("en", "uk")
DEFAULT_LANG = "en"


def normalize_lang(value: Optional[str], default: str = DEFAULT_LANG) -> str:
    """Coerce any input to a supported language code, else the default."""
    if not value:
        return default
    code = str(value).strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED else default


def lang_from_accept(header: Optional[str], default: str = DEFAULT_LANG) -> str:
    """Best-effort language from an Accept-Language header (first tag wins).

    Used only where there is no user yet (register, an unknown-email reset):
    once a user is known, ``user.language`` is authoritative.
    """
    if not header:
        return default
    first = header.split(",")[0].strip()
    return normalize_lang(first, default)


# key -> {lang -> template}. Grouped by area. Placeholders must match across
# languages. Keep additions alphabetical within a group for easy diffing.
MESSAGES: dict[str, dict[str, str]] = {
    # ── Auth / account API errors ──
    "auth.email_taken": {
        "en": "Email already registered",
        "uk": "Ця пошта вже зареєстрована",
    },
    "auth.bad_credentials": {
        "en": "Incorrect email or password",
        "uk": "Невірний email або пароль",
    },
    "auth.google_failed": {
        "en": "Could not sign in with Google",
        "uk": "Не вдалося увійти через Google",
    },
    "auth.google_unavailable": {
        "en": "Google sign-in is not available",
        "uk": "Вхід через Google недоступний",
    },
    "auth.verify_email_first": {
        "en": "Confirm your email — we've sent a code to your address.",
        "uk": "Підтвердіть пошту — ми надіслали код на вашу адресу.",
    },
    "auth.invalid_credentials_token": {
        "en": "Could not validate credentials",
        "uk": "Не вдалося підтвердити облікові дані",
    },
    # ── Email: shared chrome ──
    "email.footer": {
        "en": "Kapot&nbsp;Tracker — your car logbook. This message was sent automatically; there's no need to reply.",
        "uk": "Kapot&nbsp;Tracker — бортовий журнал авто. Цей лист надіслано автоматично, відповідати на нього не потрібно.",
    },
    "email.button_fallback": {
        "en": "Button not opening? Use this link:",
        "uk": "Кнопка не відкривається? Перейдіть за посиланням:",
    },
    # ── Email: change of address ──
    "email.change.subject": {
        "en": "Kapot Tracker — confirm your new email",
        "uk": "Kapot Tracker — підтвердження нової пошти",
    },
    "email.change.text": {
        "en": "You're changing your Kapot Tracker sign-in address to this one.\n\nConfirmation code: {code}\n\nThe code is valid for {hours} h. Until it's entered, sign-in stays on your old address.\nIf you didn't do this, just ignore this message.",
        "uk": "Ви змінюєте адресу входу в Kapot Tracker на цю.\n\nКод підтвердження: {code}\n\nКод дійсний {hours} год. Поки код не введено, вхід лишається на старій адресі.\nЯкщо ви цього не робили — просто проігноруйте цей лист.",
    },
    "email.change.heading": {
        "en": "Confirm your new email",
        "uk": "Підтвердження нової пошти",
    },
    "email.change.lede": {
        "en": "You're changing your Kapot Tracker sign-in address to this one. Enter the code in the app to finish.",
        "uk": "Ви змінюєте адресу входу в Kapot Tracker на цю. Введіть код у застосунку, щоб завершити.",
    },
    "email.change.note": {
        "en": "The code is valid for {hours} h. Until it's entered, sign-in stays on your old address. If you didn't do this, just ignore this message.",
        "uk": "Код дійсний {hours} год. Поки код не введено, вхід лишається на старій адресі. Якщо ви цього не робили — просто проігноруйте лист.",
    },
    # ── Email: address verification ──
    "email.verify.subject": {
        "en": "Kapot Tracker — confirm your email",
        "uk": "Kapot Tracker — підтвердження пошти",
    },
    "email.verify.text": {
        "en": "Welcome to Kapot Tracker!\n\nConfirm your email by following this link:\n{link}\n\nThe link is valid for {hours} h. If you didn't sign up, just ignore this message.",
        "uk": "Вітаємо в Kapot Tracker!\n\nПідтвердіть пошту за посиланням:\n{link}\n\nПосилання дійсне {hours} год. Якщо ви не реєструвалися — просто проігноруйте цей лист.",
    },
    "email.verify.heading": {
        "en": "Welcome to Kapot Tracker!",
        "uk": "Вітаємо в Kapot Tracker!",
    },
    "email.verify.lede": {
        "en": "Just confirm your email — tap the button below.",
        "uk": "Залишилось підтвердити пошту — натисніть кнопку нижче.",
    },
    "email.verify.button": {
        "en": "Confirm email",
        "uk": "Підтвердити пошту",
    },
    "email.verify.note": {
        "en": "The link is valid for {hours} h. If you didn't sign up, just ignore this message.",
        "uk": "Посилання дійсне {hours} год. Якщо ви не реєструвалися — просто проігноруйте цей лист.",
    },
    # ── Email: password reset ──
    "email.reset.subject": {
        "en": "Kapot Tracker — password reset",
        "uk": "Kapot Tracker — відновлення пароля",
    },
    "email.reset.text": {
        "en": "Your password reset code: {code}\n\nOr follow this link to set a new password:\n{link}\n\nThe code is valid for 10 minutes and works once.\nIf you didn't request a password change, just ignore this message.",
        "uk": "Код для зміни пароля: {code}\n\nАбо перейдіть за посиланням, щоб задати новий пароль:\n{link}\n\nКод дійсний 10 хвилин і працює один раз.\nЯкщо ви не просили зміну пароля — просто проігноруйте цей лист.",
    },
    "email.reset.heading": {
        "en": "Password reset",
        "uk": "Відновлення пароля",
    },
    "email.reset.lede": {
        "en": "Tap the button to set a new password, or enter the code in the app manually.",
        "uk": "Натисніть кнопку, щоб задати новий пароль, або введіть код у застосунку вручну.",
    },
    "email.reset.button": {
        "en": "Set a new password",
        "uk": "Задати новий пароль",
    },
    "email.reset.note": {
        "en": "The code is valid for 10 minutes and works once. If you didn't request a password change, just ignore this message.",
        "uk": "Код дійсний 10 хвилин і працює один раз. Якщо ви не просили зміну пароля — просто проігноруйте цей лист.",
    },
    # ── In-app notification centre (services/notifications.py) ──
    "notif.interval.overdueKm": {"en": "overdue by {km} km", "uk": "прострочено на {km} км"},
    "notif.interval.leftKm": {"en": "{km} km left", "uk": "залишилось {km} км"},
    "notif.interval.overdueDaysAgo": {"en": "{days} days ago", "uk": "{days} дн. тому"},
    "notif.interval.leftDays": {"en": "{days} days left", "uk": "залишилось {days} дн."},
    "notif.interval.alreadyOverdue": {"en": "already overdue", "uk": "вже прострочено"},
    "notif.interval.approaching": {"en": "approaching", "uk": "наближається"},
    "notif.spike.title": {"en": "Fuel consumption spike", "uk": "Стрибок витрати пального"},
    "notif.spike.body": {
        "en": "+{pct}% over normal ({actual} vs ~{baseline} L/100 km). Check tyre pressure, filters or spark plugs.",
        "uk": "+{pct}% над нормою ({actual} проти ~{baseline} л/100 км). Перевірте тиск у шинах, фільтри чи свічки.",
    },
    "notif.tireAge.title": {"en": "Tyre age", "uk": "Вік шин"},
    "notif.tireAge.body": {
        "en": "The «{name}» set is already {age} yr old — time to check its condition and maybe replace it.",
        "uk": "Комплекту «{name}» вже {age} р. — час перевірити стан і, можливо, замінити.",
    },
    "notif.rotation.title": {"en": "Tyre rotation", "uk": "Ротація шин"},
    "notif.rotation.body": {
        "en": "{km} km since the last rotation — swap the axles so the tread wears evenly.",
        "uk": "{km} км від останньої ротації — переставте вісі, щоб протектор зношувався рівномірно.",
    },
    "notif.seasonalAdd.title": {"en": "Tyre-change season", "uk": "Сезон шиномонтажу"},
    "notif.seasonalAdd.body": {
        "en": "Add your tyre set and I'll remind you about changeover, rotation and age.",
        "uk": "Додайте свій комплект шин, і я нагадуватиму про заміну, ротацію та вік.",
    },
    "notif.seasonalSwitch.title": {"en": "Time to change tyres", "uk": "Час міняти гуму"},
    "notif.seasonalSwitch.body": {
        "en": "Time to switch to {season} tyres for the season.",
        "uk": "Пора переходити на {season} гуму за сезоном.",
    },
    "notif.season.winter": {"en": "winter", "uk": "зимову"},
    "notif.season.summer": {"en": "summer", "uk": "літню"},
    "notif.insurance.titleExpiring": {"en": "Insurance expiring", "uk": "Страховка спливає"},
    "notif.insurance.titleExpired": {"en": "Insurance expired", "uk": "Страховка прострочена"},
    "notif.insurance.bodyExpired": {
        "en": "Insurance was valid until {date} — overdue by {days} days. Driving uninsured means a fine and personal liability for an accident.",
        "uk": "ОСЦПВ була дійсна до {date} — прострочено на {days} дн. Їзда без поліса — штраф і особиста відповідальність за ДТП.",
    },
    "notif.insurance.bodyExpiring": {
        "en": "Insurance valid until {date} — {days} days left. Renew the policy to avoid a fine.",
        "uk": "ОСЦПВ дійсна до {date} — лишилось {days} дн. Оновіть поліс, щоб уникнути штрафу.",
    },
    # ── API error details (routers) ──
    "err.verifyEmailForFeature": {"en": "Verify your email to use this feature.", "uk": "Підтвердіть пошту, щоб користуватися цією функцією."},
    "err.tooManyAttempts": {"en": "Too many attempts. Try again later.", "uk": "Забагато спроб. Спробуйте пізніше."},
    "err.tooManyRequests": {"en": "Too many requests. Try again later.", "uk": "Забагато запитів. Спробуйте пізніше."},
    "err.passwordWrong": {"en": "Incorrect password", "uk": "Пароль невірний"},
    "err.currentPasswordWrong": {"en": "Current password is incorrect", "uk": "Поточний пароль невірний"},
    "err.alreadyYourAddress": {"en": "That's already your address", "uk": "Це вже ваша адреса"},
    "err.emailTaken": {"en": "That address is already taken", "uk": "Ця адреса вже зайнята"},
    "err.mailNotConfigured": {
        "en": "Email isn't set up on the server — changing your address is unavailable",
        "uk": "Пошта не налаштована на сервері — зміна адреси недоступна",
    },
    "err.codeInvalidOrExpired": {"en": "Invalid or expired code", "uk": "Невірний або прострочений код"},
    "err.roleMustBe": {"en": "Role must be «editor» or «viewer»", "uk": "Роль має бути «editor» або «viewer»"},
    "err.ownCarFullAccess": {
        "en": "This is your car — you already have full access to it",
        "uk": "Це ваше авто — ви вже маєте до нього повний доступ",
    },
    "err.ownerRoleImmutable": {"en": "The car owner's role can't be changed", "uk": "Роль власника авто змінити не можна"},
    "err.ownerCantBeRemoved": {
        "en": "The car owner can't be removed from the members list",
        "uk": "Власника авто не можна прибрати зі списку учасників",
    },
    "err.onlyCarScannerCsv": {"en": "Only Car Scanner CSV export is supported", "uk": "Підтримується лише CSV-експорт Car Scanner"},
    "err.fileTooLarge20": {"en": "File too large (max 20 MB)", "uk": "Файл завеликий (максимум 20 МБ)"},
    "err.plateNotConfigured": {"en": "Plate lookup isn't set up on this server.", "uk": "Пошук за номером не налаштований на цьому сервері."},
    "err.plateServiceUnavailable": {"en": "The lookup service is temporarily unavailable.", "uk": "Сервіс пошуку тимчасово недоступний."},
    "err.plateNotFound": {"en": "No car with this plate was found in the registry.", "uk": "Авто з таким номером не знайдено в реєстрі."},
    "err.ocrUnavailable": {
        "en": "Recognition is temporarily unavailable. Enter the data manually and try scanning later.",
        "uk": "Розпізнавання тимчасово недоступне. Введіть дані вручну і спробуйте скан пізніше.",
    },
    # ── API success/info details ──
    "msg.resetCodeSentIfExists": {"en": "If the account exists, we've sent a code.", "uk": "Якщо акаунт існує — ми надіслали код."},
    "msg.passwordChanged": {"en": "Password changed", "uk": "Пароль змінено"},
    "msg.emailConfirmed": {"en": "Email confirmed", "uk": "Пошту підтверджено"},
    # ── PDF service-history report (services/report.py) ──
    "report.title": {"en": "Kapot Tracker — Service history", "uk": "Kapot Tracker — Сервісна історія"},
    "report.generated": {"en": "Report generated: {date}", "uk": "Звіт згенеровано: {date}"},
    "report.carHeading": {"en": "Car", "uk": "Авто"},
    "report.currentMileage": {"en": "Current mileage: {km}", "uk": "Поточний пробіг: {km}"},
    "report.fuelType": {"en": "Fuel type: {fuel}", "uk": "Тип пального: {fuel}"},
    "report.avgDaily": {"en": "Average daily distance: {value}", "uk": "Середній добовий пробіг: {value}"},
    "report.kmPerDay": {"en": "{km} km/day", "uk": "{km} км/день"},
    "report.spendingHeading": {"en": "Spending summary", "uk": "Підсумки витрат"},
    "report.noEntries": {"en": "No entries yet.", "uk": "Записів поки немає."},
    "report.totalAllTime": {"en": "All-time total: {money}", "uk": "Сума за весь час: {money}"},
    "report.byTypeLine": {
        "en": "Fuel-ups: {refuel} · Service: {maintenance} · Repairs: {repair} · Other: {expense}",
        "uk": "Заправки: {refuel} · ТО: {maintenance} · Ремонти: {repair} · Інші: {expense}",
    },
    "report.avgConsumption": {"en": "Average consumption: {value}", "uk": "Середній розхід: {value}"},
    "report.costPerKm": {"en": "Cost per km: {value}", "uk": "Вартість 1 км: {value}"},
    "report.dataPeriod": {"en": "Data period: {start} — {end}", "uk": "Період даних: {start} — {end}"},
    "report.serviceHistoryHeading": {"en": "Service history", "uk": "Сервісна історія"},
    "report.noServiceEntries": {"en": "No service or repair entries yet.", "uk": "Записів про ТО та ремонти поки немає."},
    "report.colDate": {"en": "Date", "uk": "Дата"},
    "report.colMileage": {"en": "Mileage", "uk": "Пробіг"},
    "report.colDescription": {"en": "Description", "uk": "Опис"},
    "report.colCost": {"en": "Cost", "uk": "Вартість"},
    "report.refuelsHeading": {"en": "Fuel-ups", "uk": "Заправки"},
    "report.noRefuels": {"en": "No fuel-ups yet.", "uk": "Заправок поки немає."},
    "report.refuelsLine": {
        "en": "Fuel-ups: {count} · Total litres: {liters} L · Total: {money}",
        "uk": "Кількість заправок: {count} · Всього літрів: {liters} л · Всього: {money}",
    },
    "report.intervalsHeading": {"en": "Service intervals", "uk": "Сервісні інтервали"},
    "report.noIntervals": {"en": "No service intervals yet.", "uk": "Сервісних інтервалів поки немає."},
    "report.colName": {"en": "Name", "uk": "Назва"},
    "report.colLast": {"en": "Last done", "uk": "Останнє виконання"},
    "report.colNext": {"en": "Next", "uk": "Наступне"},
    "report.colStatus": {"en": "Status", "uk": "Статус"},
    "report.page": {"en": "Page {n}", "uk": "Сторінка {n}"},
    "report.status.ok": {"en": "OK", "uk": "ОК"},
    "report.status.dueSoon": {"en": "soon", "uk": "скоро"},
    "report.status.overdue": {"en": "overdue", "uk": "прострочено"},
    "report.unitKm": {"en": "km", "uk": "км"},
    "report.unitUah": {"en": "UAH", "uk": "грн"},
    "report.unitConsumption": {"en": "L/100 km", "uk": "л/100 км"},
    "report.unitUahPerKm": {"en": "UAH/km", "uk": "грн/км"},
    # ── Year review (services/year_review.py) biggest-entry fallback labels ──
    "yr.repair": {"en": "Repair", "uk": "Ремонт"},
    "yr.expense": {"en": "Expense", "uk": "Витрата"},
    "yr.refuel": {"en": "Fuel-up", "uk": "Заправка"},
    "yr.service": {"en": "Service", "uk": "ТО"},
    "yr.unnamedStation": {"en": "Unnamed station", "uk": "Без назви"},
    "yr.entry": {"en": "Entry", "uk": "Запис"},
    # --- BOT MESSAGES (generated by merge-bot.mjs) ---
    "bot.cmd.backup": {"en": "Database backup (admin)", "uk": "Резервна копія бази (адмін)"},
    "bot.cmd.help": {"en": "Help and message formats", "uk": "Довідка та формати повідомлень"},
    "bot.cmd.note": {"en": "Notepad: codes, phones, PINs", "uk": "Блокнот: коди, телефони, PIN"},
    "bot.cmd.report": {"en": "PDF report for your car", "uk": "PDF-звіт по авто"},
    "bot.cmd.start": {"en": "Link your Kapot Tracker account", "uk": "Прив'язати акаунт Kapot Tracker"},
    "bot.cmd.status": {"en": "Car status and upcoming service", "uk": "Стан авто та найближчі ТО"},
    "bot.h.adminOnly": {"en": "This command is available to the admin only.", "uk": "Команда доступна лише адміністратору."},
    "bot.h.askExpense": {"en": "Send an expense: «car wash 300».", "uk": "Надішліть витрату: «мийка 300»."},
    "bot.h.askOdometer": {"en": "Send the current mileage — just the number, e.g. 240054.", "uk": "Надішліть поточний пробіг — просто числом, напр. 240054."},
    "bot.h.askRefuel": {"en": "Send a fuel-up: «fuel 45L 2500» or a receipt photo.", "uk": "Надішліть заправку: «заправка 45л 2500» або фото чека."},
    "bot.h.backupFailed": {"en": "Couldn't create the backup. Try again later.", "uk": "Не вдалося зробити бекап. Спробуйте пізніше."},
    "bot.h.backupPreparing": {"en": "Preparing a database backup…", "uk": "Готую резервну копію бази…"},
    "bot.h.badData": {"en": "Invalid data", "uk": "Некоректні дані"},
    "bot.h.btnExpense": {"en": "💸 Expense", "uk": "💸 Витрата"},
    "bot.h.btnHelp": {"en": "❓ Help", "uk": "❓ Довідка"},
    "bot.h.btnOdometer": {"en": "🛣 Mileage", "uk": "🛣 Пробіг"},
    "bot.h.btnRefuel": {"en": "⛽ Fuel-up", "uk": "⛽ Заправка"},
    "bot.h.btnReport": {"en": "📄 Report", "uk": "📄 Звіт"},
    "bot.h.btnStatus": {"en": "📊 Status", "uk": "📊 Стан"},
    "bot.h.cancelButton": {"en": "Cancel", "uk": "Скасувати"},
    "bot.h.cancelled": {"en": "Cancelled. Nothing saved.", "uk": "Скасовано. Нічого не збережено."},
    "bot.h.carLine": {"en": "- {label}, {odometer} km", "uk": "- {label}, {odometer} км"},
    "bot.h.carNotFound": {"en": "Car not found.", "uk": "Авто не знайдено."},
    "bot.h.carNotFoundToast": {"en": "Car not found", "uk": "Авто не знайдено"},
    "bot.h.carWithOdometer": {"en": "Car: {label} (mileage {odometer} km)", "uk": "Авто: {label} (пробіг {odometer} км)"},
    "bot.h.dateLine": {"en": "Date: {date}", "uk": "Дата: {date}"},
    "bot.h.digestOff": {"en": "Weekly digest disabled. Turn it back on: /digest on", "uk": "Тижневий дайджест вимкнено. Увімкнути назад: /digest on"},
    "bot.h.digestOn": {"en": "Weekly digest enabled. Every Sunday I'll send a summary of the week for each car — expenses, mileage, consumption and the next service. No digest for a week with no entries.", "uk": "Тижневий дайджест увімкнено. Щонеділі надсилатиму підсумок тижня по кожному авто — витрати, пробіг, розхід і найближче ТО. За тиждень без записів дайджесту не буде."},
    "bot.h.digestState": {"en": "Weekly digest: {state}.\nChange it: /digest on or /digest off", "uk": "Тижневий дайджест: {state}.\nЗмінити: /digest on або /digest off"},
    "bot.h.digestStateOff": {"en": "off", "uk": "вимкнено"},
    "bot.h.digestStateOn": {"en": "on", "uk": "увімкнено"},
    "bot.h.expenseConfirm": {"en": "Expense: «{title}» — {amount:.2f} {currency}\nCar: {label}\nDate: {date}\n\nSave?", "uk": "Витрата: «{title}» — {amount:.2f} {currency}\nАвто: {label}\nДата: {date}\n\nЗберегти?"},
    "bot.h.expenseSaved": {"en": "Expense saved: «{title}» — {amount:.2f} {currency} ({date}).", "uk": "Витрату збережено: «{title}» — {amount:.2f} {currency} ({date})."},
    "bot.h.expired": {"en": "This entry has expired. Send it again.", "uk": "Запис застарів. Надішліть його ще раз."},
    "bot.h.help": {"en": "Available commands:\n/start <code> — link your Kapot Tracker account\n/status — car status and upcoming service\n/report — PDF report for a car\n/digest on|off — weekly summary on Sunday\n/help — this help\n\nYou can also just send:\n- «mileage 240054» — update the mileage;\n- «car wash 300» — a quick expense;\n- «fuel 45L 2500» — a fuel-up entry;\n- a receipt photo — I'll read the fuel-up automatically.", "uk": "Доступні команди:\n/start <код> — прив'язати акаунт Kapot Tracker\n/status — стан авто та найближчі ТО\n/report — PDF-звіт по авто\n/digest on|off — тижневий підсумок у неділю\n/help — ця довідка\n\nТакож можна просто надіслати:\n- «пробіг 240054» — оновити пробіг;\n- «мийка 300» — швидка витрата;\n- «заправка 45л 2500» — запис про заправку;\n- фото чека — розпізнаю заправку автоматично."},
    "bot.h.intervalDone": {"en": "Logged: «{title}» done at {odometer} km ({date}). The countdown has restarted — you can add the details and cost in the web app.", "uk": "Записав: «{title}» виконано на {odometer} км ({date}). Відлік почато заново — деталі та вартість можна дописати у веб-додатку."},
    "bot.h.intervalNotFound": {"en": "Interval not found", "uk": "Інтервал не знайдено"},
    "bot.h.intervalSnoozed": {"en": "OK, I'll remind you about «{title}» in 7 days.", "uk": "Добре, нагадаю про «{title}» через 7 днів."},
    "bot.h.invalidCode": {"en": "The code is invalid or expired. Generate a new one in the Kapot Tracker web app («Garage») and send /start <code> again.", "uk": "Код недійсний або прострочений. Згенеруйте новий у веб-додатку Kapot Tracker (розділ «Гараж») і надішліть /start <код> ще раз."},
    "bot.h.linkedNoCars": {"en": "Account linked! No cars in your garage yet — add your first one in the Kapot Tracker web app.", "uk": "Акаунт прив'язано! У гаражі поки немає авто — додайте перше у веб-додатку Kapot Tracker."},
    "bot.h.linkedWithCars": {"en": "Account linked! Your cars:\n{cars}\n\nUse the buttons below or send /help.", "uk": "Акаунт прив'язано! Ваші авто:\n{cars}\n\nКористуйтеся кнопками нижче або надішліть /help."},
    "bot.h.linkHint": {"en": "To link your account, open the Kapot Tracker web app, go to «Garage», generate a code and send it here with:\n/start <code>", "uk": "Щоб прив'язати акаунт, відкрийте веб-додаток Kapot Tracker, розділ «Гараж», згенеруйте код і надішліть його сюди командою:\n/start <код>"},
    "bot.h.maintenanceHeader": {"en": "Service order for {total:.2f} {currency}", "uk": "Наряд СТО на {total:.2f} {currency}"},
    "bot.h.maintenanceMore": {"en": "…and {count} more", "uk": "…та ще {count}"},
    "bot.h.maintenancePartsLabor": {"en": "Parts: {parts:.2f} {currency} · Labour: {labor:.2f} {currency}", "uk": "Запчастини: {parts:.2f} {currency} · Роботи: {labor:.2f} {currency}"},
    "bot.h.maintenanceSaved": {"en": "Service saved: {total:.2f} {currency}, {count} items ({date}), mileage {odometer} km.", "uk": "ТО збережено: {total:.2f} {currency}, {count} позицій ({date}), пробіг {odometer} км."},
    "bot.h.msgExpired": {"en": "This message has expired", "uk": "Повідомлення застаріло"},
    "bot.h.noCars": {"en": "No cars in your garage yet. Add your first car in the Kapot Tracker web app.", "uk": "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."},
    "bot.h.noteEmpty": {"en": "No notes yet. Write, for example:\n/note yard gate — code 1234, garage 067 000 00 00", "uk": "Нотаток ще немає. Напишіть, наприклад:\n/note ворота у дворі — код 1234, СТО 067 000 00 00"},
    "bot.h.noteMultiCar": {"en": "You have several cars — edit the note in the app (Settings → car → Edit).", "uk": "У вас кілька авто — відредагуйте нотатку в застосунку (Налаштування → авто → Редагувати)."},
    "bot.h.noteNoCars": {"en": "Add a car in the app first.", "uk": "Спочатку додайте авто у застосунку."},
    "bot.h.noteSaved": {"en": "📝 Note for {label} saved.", "uk": "📝 Нотатку до {label} збережено."},
    "bot.h.notLinkedIntro": {"en": "Your Telegram isn't linked to a Kapot Tracker account yet.", "uk": "Ваш Telegram ще не прив'язано до акаунта Kapot Tracker."},
    "bot.h.ocrFailed": {"en": "Couldn't read the data from the photo. Try shooting the receipt straighter and in better light, or send the fuel-up as text, for example: заправка 45л 2500", "uk": "Не вдалося розпізнати дані на фото. Спробуйте зняти чек рівніше і при кращому світлі або надішліть заправку текстом, наприклад: заправка 45л 2500"},
    "bot.h.ocrPartialTotal": {"en": "I only read the amount: {total:.2f} {currency}.\nSend the fuel-up as text, e.g.: заправка 45л {total:.0f}", "uk": "Прочитав лише суму: {total:.2f} {currency}.\nНадішліть заправку текстом, напр.: заправка 45л {total:.0f}"},
    "bot.h.ocrUnavailable": {"en": "Couldn't read the receipt: tesseract isn't installed on the server. Send the fuel-up as text, for example: заправка 45л 2500", "uk": "Не вдалося розпізнати чек: на сервері не встановлено tesseract. Надішліть заправку текстом, наприклад: заправка 45л 2500"},
    "bot.h.odometerBackwards": {"en": "Can't update: the new mileage ({value} km) is lower than the current one ({old} km), and mileage can't go down. Check the value and send it again.", "uk": "Не можу оновити: новий пробіг ({value} км) менший за поточний ({old} км), а пробіг не може зменшуватися. Перевірте значення і надішліть ще раз."},
    "bot.h.odometerUpdated": {"en": "Mileage for {label} updated: {old} km -> {new} km.", "uk": "Пробіг {label} оновлено: {old} км -> {new} км."},
    "bot.h.photoWillBeAdded": {"en": "The receipt photo will be attached to the entry.", "uk": "Фото чека буде додано до запису."},
    "bot.h.recognizingPhoto": {"en": "Reading the photo", "uk": "Розпізнаю фото"},
    "bot.h.refuelLine": {"en": "Fuel-up: {liters:.2f} L × {price:.2f} {currency}/L = {total:.2f} {currency}", "uk": "Заправка: {liters:.2f} л × {price:.2f} {currency}/л = {total:.2f} {currency}"},
    "bot.h.refuelPhotoSuffix": {"en": " Receipt photo attached.", "uk": " Фото чека додано."},
    "bot.h.refuelSaved": {"en": "Fuel-up saved: {liters:.2f} L for {total:.2f} {currency} ({date}), mileage {odometer} km.{suffix}", "uk": "Заправку збережено: {liters:.2f} л на {total:.2f} {currency} ({date}), пробіг {odometer} км.{suffix}"},
    "bot.h.reportCaption": {"en": "Report: {label}", "uk": "Звіт: {label}"},
    "bot.h.rotationFailed": {"en": "Couldn't record the rotation", "uk": "Не вдалося записати ротацію"},
    "bot.h.saveButton": {"en": "Save", "uk": "Зберегти"},
    "bot.h.savePrompt": {"en": "\nSave?", "uk": "\nЗберегти?"},
    "bot.h.stationLine": {"en": "Station: {station}", "uk": "АЗС: {station}"},
    "bot.h.tireRotated": {"en": "🛞 Axle rotation logged. Next reminder in 10,000 km.", "uk": "🛞 Записав ротацію вісей. Наступне нагадування — через 10 000 км."},
    "bot.h.unknown": {"en": "I didn't understand that. Here's what I can do:\n- «mileage 240054» — update the mileage;\n- «car wash 300» — a quick expense;\n- «fuel 45L 2500» — a fuel-up entry;\n- a receipt photo — I'll read the fuel-up automatically;\n- /status — car status and upcoming service;\n- /report — PDF report for a car;\n- /help — help.", "uk": "Не зрозумів повідомлення. Ось що я вмію:\n- «пробіг 240054» — оновити пробіг;\n- «мийка 300» — швидка витрата;\n- «заправка 45л 2500» — запис про заправку;\n- фото чека — розпізнаю заправку автоматично;\n- /status — стан авто та найближчі ТО;\n- /report — PDF-звіт по авто;\n- /help — довідка."},
    "bot.h.upcomingService": {"en": "\nUpcoming service:", "uk": "\nНайближчі ТО:"},
    "bot.h.viewOnly": {"en": "You have view-only access to this car, so I can't save the entry. You can always check the car's status and upcoming service: /status.\n\nIf you need to keep records, ask the car owner to change your role to «Editor» in the Kapot Tracker web app.", "uk": "До цього авто у вас доступ лише для перегляду, тому я не можу зберегти запис. Стан авто і найближчі ТО завжди можна подивитися: /status.\n\nЯкщо потрібно вести записи — попросіть власника авто змінити вашу роль на «Редактор» у веб-додатку Kapot Tracker."},
    "bot.h.whichCarExpense": {"en": "Which car should I log the expense «{title}» of {amount:.2f} {currency} to?", "uk": "До якого авто записати витрату «{title}» на {amount:.2f} {currency}?"},
    "bot.h.whichCarMaintenance": {"en": "Which car should I log the service of {total:.2f} {currency} to?", "uk": "До якого авто записати ТО на {total:.2f} {currency}?"},
    "bot.h.whichCarOdometer": {"en": "Which car should I update the mileage to {value} km for?", "uk": "Для якого авто оновити пробіг до {value} км?"},
    "bot.h.whichCarRefuel": {"en": "Which car should I log the fuel-up of {total:.2f} {currency} to?", "uk": "До якого авто записати заправку на {total:.2f} {currency}?"},
    "bot.h.whichCarReport": {"en": "Which car should I prepare a report for?", "uk": "Для якого авто підготувати звіт?"},
    "bot.rem.btn_add_tires": {"en": "🛞 Add tyres", "uk": "🛞 Додати шини"},
    "bot.rem.btn_do_rotation": {"en": "🛞 Rotate tyres", "uk": "🛞 Зробити ротацію"},
    "bot.rem.btn_open_tires": {"en": "🛞 Open tyres", "uk": "🛞 Відкрити шини"},
    "bot.rem.car_header": {"en": "\n{brand} {model} (odometer {odo} km):", "uk": "\n{brand} {model} (пробіг {odo} км):"},
    "bot.rem.consumption": {"en": "⛽ {brand} {model}: spotted a spike in {fuel} consumption of {pct}% — {cons} L/100 km vs the usual ~{baseline}.\nIf your driving style hasn't changed, it's worth checking tyre pressure, and the state of the particulate filter or spark plugs.", "uk": "⛽ {brand} {model}: помічено стрибок витрати {fuel} на {pct}% — {cons} л/100 км проти звичних ~{baseline}.\nЯкщо стиль їзди не змінювався, варто перевірити тиск у шинах, а також стан сажового фільтра чи свічок."},
    "bot.rem.done_button": {"en": "Done", "uk": "Виконано"},
    "bot.rem.fuel_default": {"en": "fuel", "uk": "пального"},
    "bot.rem.fuel_diesel": {"en": "diesel", "uk": "дизеля"},
    "bot.rem.fuel_electric": {"en": "electricity", "uk": "електрики"},
    "bot.rem.fuel_hybrid": {"en": "fuel", "uk": "пального"},
    "bot.rem.fuel_lpg": {"en": "LPG", "uk": "газу"},
    "bot.rem.fuel_petrol": {"en": "petrol", "uk": "бензину"},
    "bot.rem.header": {"en": "Kapot Tracker reminder: a service is coming up or already overdue.", "uk": "Нагадування Kapot Tracker: наближається або вже прострочене ТО."},
    "bot.rem.odometer_nudge": {"en": "\nAlso: no new entries in a while. Send «пробіг 240054» — that keeps the forecasts sharp.", "uk": "\nІ ще: давно не було нових записів. Надішліть «пробіг 240054» — так прогнози будуть точнішими."},
    "bot.rem.rotation": {"en": "🛞 {brand} {model}: the {which} has done {km} km since the last rotation. It's worth swapping the wheels around (rear axle to the front) so the tread wears evenly. Done it? Tap the button below.", "uk": "🛞 {brand} {model}: {which} проїхав уже {km} км від останньої ротації. Рекомендовано переставити колеса місцями (задню вісь наперед), щоб протектор зношувався рівномірно. Зробили — тапніть кнопку нижче."},
    "bot.rem.season_all": {"en": "all-season", "uk": "всесезонний"},
    "bot.rem.season_summer": {"en": "summer", "uk": "літній"},
    "bot.rem.season_winter": {"en": "winter", "uk": "зимовий"},
    "bot.rem.seasonal_tires": {"en": "🛞 {brand} {model}: winter is coming, but the car still has summer tyres. Worth booking a tyre-fitting slot before the two-week queues set in.", "uk": "🛞 {brand} {model}: наближається зима, а на авто досі літня гума. Варто записатися на шиномонтаж, поки немає двотижневих черг."},
    "bot.rem.seasonal_tires_add": {"en": "🛞 {brand} {model}: tyre-change season — time to look after your tyres. Add your tyre set in the app and I'll remind you about seasonal changeover, axle rotation and tyre age.", "uk": "🛞 {brand} {model}: сезон шиномонтажу — час подбати про гуму. Додайте свій комплект шин у застосунку, і я нагадуватиму про сезонну заміну, ротацію вісей і вік шин."},
    "bot.rem.seasonal_washer": {"en": "🥶 The first overnight frosts are approaching in your region. Don't forget to spray out the summer water and fill up with winter fluid (-20 °C), so the washer tubes and pump motor don't burst.", "uk": "🥶 Наближаються перші нічні заморозки у вашому регіоні. Не забудьте вибризкати літню воду й залити зимову рідину (-20 °C), щоб не розірвало трубки й моторчик омивача скла."},
    "bot.rem.snooze_button": {"en": "Remind me in 7 days", "uk": "Нагадати через 7 днів"},
    "bot.rem.tire_age": {"en": "🛞 {brand} {model}: the «{name}» set is already {age} yr old. Rubber hardens and cracks with age — worth checking its condition and maybe replacing it, even if there's still tread left.", "uk": "🛞 {brand} {model}: комплекту «{name}» уже {age} р. Гума з віком твердне й тріскається — варто перевірити стан і, можливо, замінити, навіть якщо протектор ще лишився."},
    "bot.rem.tire_set_named": {"en": "{season} tyre set", "uk": "{season} комплект шин"},
    "bot.svc.consumption": {"en": "Average consumption: {value} L/100 km", "uk": "Середній розхід: {value} л/100км"},
    "bot.svc.digestHeader": {"en": "📊 Your week with Kapot — {label}", "uk": "📊 Тиждень з Kapot — {label}"},
    "bot.svc.distance": {"en": "Distance: +{km} km", "uk": "Пробіг: +{km} км"},
    "bot.svc.emptyGarage": {"en": "No cars in your garage yet. Add your first car in the Kapot Tracker web app.", "uk": "У гаражі поки немає авто. Додайте перше авто у веб-додатку Kapot Tracker."},
    "bot.svc.inDays": {"en": "in {days} days", "uk": "через {days} дн."},
    "bot.svc.inKm": {"en": "in {km} km", "uk": "через {km} км"},
    "bot.svc.intervalsNotSet": {"en": "No service intervals set up.", "uk": "Інтервали ТО не налаштовані."},
    "bot.svc.leftDays": {"en": "{days} days left", "uk": "залишилось {days} дн."},
    "bot.svc.leftKm": {"en": "{km} km left", "uk": "залишилось {km} км"},
    "bot.svc.nearest": {"en": "Next service: {phrase}", "uk": "Найближче ТО: {phrase}"},
    "bot.svc.noLimit": {"en": "no distance or date limit", "uk": "без прив'язки до пробігу чи дати"},
    "bot.svc.overdueDays": {"en": "overdue by {days} days", "uk": "прострочено на {days} дн."},
    "bot.svc.overdueKm": {"en": "overdue by {km} km", "uk": "прострочено на {km} км"},
    "bot.svc.shared": {"en": "(shared)", "uk": "(спільне)"},
    "bot.svc.spent": {"en": "Spent {money}", "uk": "Витрачено {money}"},
    "bot.svc.statusCarLine": {"en": "{label} — odometer {km} km", "uk": "{label} — пробіг {km} км"},
    "bot.svc.typeExpense": {"en": "other", "uk": "інші"},
    "bot.svc.typeMaintenance": {"en": "service", "uk": "ТО"},
    "bot.svc.typeRefuel": {"en": "fuel", "uk": "заправки"},
    "bot.svc.typeRepair": {"en": "repair", "uk": "ремонт"},
    # --- end BOT MESSAGES ---
}


def t(key: str, lang: Optional[str] = DEFAULT_LANG, **kwargs) -> str:
    """Translate ``key`` into ``lang`` (falling back to English, then the key)."""
    code = normalize_lang(lang)
    entry = MESSAGES.get(key)
    if not entry:
        return key
    template = entry.get(code) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template
