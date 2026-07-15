/** @type {import('tailwindcss').Config} */

// Дизайн-система Kapot Tracker. Джерело — світ продукту: нічний гараж,
// термопапір чека і бурштин приладової панелі. Бурштин — єдиний яскравий
// акцент; синій лишається тільки за Telegram; папір з'являється там, де в
// інтерфейсі є справжній чек.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        garage: '#0B1119', // тло застосунку
        panel: '#121A26', // картки й панелі
        raised: '#0D1520', // поля введення всередині карток
        edge: '#1D2A3E', // межі
        'edge-soft': '#223044', // межі другого рівня
        amber: {
          DEFAULT: '#FFB454', // акцент + попередження
          deep: '#E8912B',
          ink: '#231708', // текст на бурштині
        },
        signal: '#4C8DFF', // Telegram / інформаційне
        paper: {
          DEFAULT: '#F2EEE3', // термопапір
          dim: '#E7E1D2',
        },
        ink: {
          DEFAULT: '#23201A', // касова фарба на папері
          soft: '#5A544A',
        },
        mist: '#93A1B8', // приглушений текст
        fg: '#E9EEF6', // основний текст
        ok: '#35C77B',
        crit: '#FF5D5D',
      },
      fontFamily: {
        display: ['Unbounded', 'system-ui', 'sans-serif'],
        sans: ['IBM Plex Sans', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
