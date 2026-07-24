// Vercel Edge Middleware — geo-block. Runs on every request at Vercel's edge,
// before the SPA is served. Visitors geolocated to the aggressor states get the
// static /for-occupants.html and nothing else; everyone else passes through.
//
// Zero-dependency: uses the Web-standard Request/Response and Vercel's
// `x-middleware-rewrite` header instead of the @vercel/edge helpers, so nothing
// needs installing.
//
// This is a stance, not hard security: a VPN trivially bypasses it, and the API
// (on a separate host) isn't gated here. It stops the app from loading for those
// IPs, which is the intent.

export const config = {
  // Run on everything EXCEPT the block page itself, static assets, and Vercel
  // internals — so the rewrite target can be served and we never loop.
  matcher: ['/((?!for-occupants\\.html|assets/|fonts/|_vercel|favicon).*)'],
};

// Aggressor states. RU = russia, BY = belarus (co-aggressor launching pad).
const BLOCKED = new Set(['RU', 'BY']);

export default function middleware(request: Request): Response {
  // Vercel populates this header with the edge-detected ISO country code.
  const country = (request.headers.get('x-vercel-ip-country') || '').toUpperCase();

  if (BLOCKED.has(country)) {
    const url = new URL('/for-occupants.html', request.url);
    return new Response(null, {
      headers: { 'x-middleware-rewrite': url.toString() },
    });
  }

  // Not blocked — let the request continue to the app untouched.
  return new Response(null, { headers: { 'x-middleware-next': '1' } });
}
