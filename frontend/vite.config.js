import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: [
        'icon.svg',
        'icon-192.png',
        'icon-512.png',
        'icon-maskable-512.png',
        'apple-touch-icon.png',
      ],
      workbox: {
        // Типовий набір Workbox не містить woff2, тож встановлений застосунок
        // офлайн лишався б без своїх шрифтів і падав на системний.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            // GET-читання API: мережа має пріоритет, але вже за 3 с показуємо
            // останню відому відповідь — на заправці «крутилка» назавжди гірша
            // за вчорашній пробіг. Функція серіалізується в sw.js як є, тож
            // усі значення всередині — без зовнішніх змінних.
            urlPattern: ({ url, request, sameOrigin }) => {
              if (!sameOrigin || request.method !== 'GET') return false;
              if (!url.pathname.startsWith('/api/')) return false;
              // /api/auth — токени й коди, /api/export, /api/photos і
              // /api/documents — бінарні відповіді: кешувати нічого з цього не
              // можна й не варто. Список документів авто (/api/cars/N/documents)
              // під цей префікс не підпадає — він JSON і кешується.
              return !['/api/auth', '/api/export', '/api/photos', '/api/documents'].some(
                (prefix) => url.pathname.startsWith(prefix),
              );
            },
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              networkTimeoutSeconds: 3,
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 86400,
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
        ],
      },
      manifest: {
        name: 'Kapot Tracker',
        short_name: 'Kapot',
        description: 'Журнал обслуговування та витрат вашого авто',
        theme_color: '#0B1119',
        background_color: '#0B1119',
        display: 'standalone',
        // Без цього плагін пише lang: 'en' — інтерфейс український, як і
        // <html lang="uk">.
        lang: 'uk',
        icons: [
          {
            src: '/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          {
            // Окремий файл, а не той самий 512: під маскою платформи кути
            // обрізаються, тож глиф зменшений у безпечну зону (80%), а тло —
            // суцільне, на весь квадрат.
            src: '/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'node',
  },
});
