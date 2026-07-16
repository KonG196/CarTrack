// Several small tours, one per section, instead of one long walk. Each step
// spotlights the element carrying `data-tour="<target>"`. `path` moves the tour
// to another route first (the engine navigates and waits for the element to
// mount); a step whose element never appears is skipped, so an empty logbook or
// a car with no analytics does not dead-end the tour.
//
// `path` may be a function of a small context ({ firstLogId }) for routes that
// need a real id — the logbook detail. Returning null skips the step.
//
// `tap: true` plays a looping «finger tap» gesture over the spotlight — use it
// on steps whose element is meant to be pressed. `demo` is a CSS selector,
// queried inside the target, that the overlay actually clicks once per step so
// the real in-place result plays (e.g. the copy icon turning into a checkmark).
// Only give `demo` to interactions that change state in place — never ones that
// navigate away or open a modal, which would break the tour.

const DEMO_COPY = '[data-tour-demo="copy"]';

export const TOURS = {
  home: {
    label: 'Головний екран',
    steps: [
      {
        target: 'car-switcher',
        tap: true,
        title: 'Ваші авто',
        body: 'Тут активне авто. Натисніть, щоб перемкнутися між машинами або додати нову.',
      },
      {
        target: 'car-name',
        tap: true,
        demo: DEMO_COPY,
        title: 'Дані для магазину',
        body: 'Натисніть на назву авто — VIN, двигун і допуски скопіюються одним рядком. Дивіться: іконка стане галочкою, коли скопійовано.',
      },
      {
        target: 'odometer',
        tap: true,
        title: 'Пробіг',
        body: 'Олівець біля пробігу відкриває редагування авто, щоб оновити кілометраж.',
      },
      {
        target: 'stats',
        title: 'Головні цифри',
        body: 'Витрати за місяць, розхід пального і вартість кілометра — рахуються самі з ваших записів.',
      },
      {
        target: 'interval-row',
        tap: true,
        title: 'Натисніть на інтервал',
        body: 'Коли зробили роботу — натисніть на цей інтервал. Відкриється форма «Виконано», робота запишеться в історію, а прогрес скинеться. Нагадування про наближення прийде у Telegram.',
      },
    ],
  },

  logbook: {
    label: 'Журнал',
    steps: [
      {
        path: '/logbook',
        target: 'logbook-search',
        title: 'Пошук',
        body: 'Знайдіть запис за назвою, АЗС чи нотаткою.',
      },
      {
        path: '/logbook',
        target: 'logbook-filters',
        tap: true,
        title: 'Фільтри',
        body: 'Лише заправки, ТО, ремонти чи витрати — або всі разом.',
      },
      {
        path: '/logbook',
        target: 'log-row',
        tap: true,
        title: 'Запис',
        body: 'Натисніть на запис, щоб відкрити деталі, фото й редагування.',
      },
      {
        path: (ctx) => (ctx.firstLogId ? `/logbook/${ctx.firstLogId}` : null),
        target: 'log-detail',
        title: 'Деталі запису',
        body: 'Повна інформація, прикріплене фото чека, а також редагування й видалення.',
      },
    ],
  },

  add: {
    label: 'Додавання запису',
    steps: [
      {
        path: '/add',
        target: 'add-type',
        tap: true,
        title: 'Тип запису',
        body: 'Заправка, ТО, ремонт або витрата — кожен зі своїми полями.',
      },
      {
        path: '/add',
        target: 'add-scan',
        tap: true,
        title: 'Сканування',
        body: 'Сфотографуйте чек АЗС або наряд СТО — суми, дата й позиції розпізнаються самі.',
      },
      {
        path: '/add',
        target: 'add-form',
        title: 'Решта полів',
        body: 'Пробіг підставляється автоматично. Заповніть, що треба, і збережіть.',
      },
    ],
  },

  analytics: {
    label: 'Аналітика',
    steps: [
      {
        path: '/analytics?tab=costs',
        target: 'analytics-forecast',
        title: 'Прогноз',
        body: 'Середні витрати за місяць, прогноз на поточний і найближчі ТО з орієнтовною ціною.',
      },
      {
        path: '/analytics?tab=costs',
        target: 'analytics-charts',
        title: 'Витрати за місяцями',
        body: 'На вкладці «Витрати» — графік за місяцями й розбивка за категоріями. Видно тренд одразу.',
      },
      {
        path: '/analytics?tab=fuel',
        target: 'analytics-trip',
        title: 'Вкладка «Паливо»',
        body: 'Тут розхід і ціна пального, а ще калькулятор поїздки: «скільки скидаємось на пальне» з реального розходу вашого авто.',
      },
      {
        path: '/analytics?tab=fuel',
        target: 'analytics-report',
        tap: true,
        title: 'PDF-звіт',
        body: 'Уся історія обслуговування одним файлом — зручно як передпродажний паспорт. А вкладка «Ефективність» покаже вартість кілометра.',
      },
    ],
  },

  settings: {
    label: 'Налаштування',
    steps: [
      {
        path: '/garage',
        target: 'settings-cars',
        tap: true,
        demo: DEMO_COPY,
        title: 'Ваші авто',
        body: 'Кожне авто: редагування, звіт, видалення. Натисніть на назву — скопіюються дані для магазину.',
      },
      {
        path: '/garage',
        target: 'settings-profile',
        tap: true,
        title: 'Профіль',
        body: 'Імʼя, пошта, пароль і привʼязка Telegram.',
      },
      {
        path: '/profile',
        target: 'profile-telegram',
        tap: true,
        title: 'Telegram-бот',
        body: 'Привʼяжіть бота — і нагадування про ТО почнуть приходити в чат.',
      },
      {
        path: '/notifications',
        target: 'notif-reminders',
        tap: true,
        title: 'Сповіщення',
        body: 'Тут вмикаються нагадування про ТО й щотижневий підсумок.',
      },
      {
        path: '/garage',
        target: 'settings-more',
        title: 'І ще',
        body: 'Документи, шини, діагностика OBD, експорт даних — усе тут, на сторінці налаштувань.',
      },
    ],
  },
};

// The order tours appear in the Settings launcher.
export const TOUR_ORDER = ['home', 'logbook', 'add', 'analytics', 'settings'];
