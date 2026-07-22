import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const LANDING_FILE = fileURLToPath(new URL('./public/landing.html', import.meta.url));

// Serve the static marketing page (public/landing.html) at a clean /welcome in
// dev and `vite preview`. In production nginx does the same map (see
// nginx.conf) — so the URL is identical everywhere and the page needs no build
// step. Registered before Vite's own middlewares so it beats the SPA history
// fallback, which would otherwise answer /welcome with index.html.
function landingRoute() {
  const serve = (req, res, next) => {
    const path = (req.url || '').split('?')[0];
    if (path === '/welcome' || path === '/welcome/') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end(readFileSync(LANDING_FILE));
      return;
    }
    next();
  };
  return {
    name: 'kapot-landing-route',
    // Block bodies on purpose: a value returned from configureServer is taken
    // as a post-hook, and server.middlewares.use() returns the connect app —
    // which Vite would then call as middleware and crash on.
    configureServer(server) {
      server.middlewares.use(serve);
    },
    configurePreviewServer(server) {
      server.middlewares.use(serve);
    },
  };
}

export default defineConfig({
  plugins: [
    landingRoute(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: [
        'favicon-16.png',
        'favicon-32.png',
        'icon-192.png',
        'icon-512.png',
        'icon-maskable-512.png',
        'apple-touch-icon.png',
        'logo-mark.png',
      ],
      workbox: {
        // Типовий набір Workbox не містить woff2, тож встановлений застосунок
        // офлайн лишався б без своїх шрифтів і падав на системний.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Не підміняти лендінг застосунком: без цього навігація на /welcome і
        // /landing.html падала б у navigateFallback (index.html) — і замість
        // сторінки відкривався б React-застосунок.
        navigateFallbackDenylist: [/^\/welcome$/, /^\/landing\.html$/],
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
        start_url: '/',
        scope: '/',
        // Мобільний портретний макет (max-w-md) — ландшафт лише розтягнув би
        // порожні поля, тож фіксуємо орієнтацію.
        orientation: 'portrait',
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
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        // 127.0.0.1, not localhost: on IPv6-first hosts «localhost» resolves to
        // ::1 and the proxy gets ECONNREFUSED while uvicorn listens on IPv4.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'node',
    setupFiles: ['./src/test-setup.js'],
  },
});
