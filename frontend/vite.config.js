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
            // Network first, but a three-second wait beats a spinner at a
            // pump: yesterday's odometer is worth more than nothing.
            // Any origin: the API sits on this one when nginx serves the app
            // and on another when a CDN does. The page only ever calls our own
            // API, so matching the path alone is both enough and honest.
            urlPattern: ({ url, request }) => {
              if (request.method !== 'GET') return false;
              if (!url.pathname.startsWith('/api/')) return false;
              // Tokens and codes under /api/auth, and the binary bodies of
              // /api/export, /api/photos and /api/documents, are never cached.
              // A car's document list (/api/cars/N/documents) does not match
              // that prefix — it is JSON and is cached.
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
