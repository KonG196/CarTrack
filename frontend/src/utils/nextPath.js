
const CONTROL_MAX = 0x20;

export function safeNext(value, fallback = '/') {
  if (typeof value !== 'string') return fallback;

  const path = Array.from(value)
    .filter((ch) => ch.charCodeAt(0) > CONTROL_MAX)
    .join('');

  if (!path.startsWith('/')) return fallback;

  if (path.startsWith('//') || path.startsWith('/\\')) return fallback;

  return path;
}

export function withNext(to, next) {
  const target = safeNext(next);
  if (target === '/') return to;
  return `${to}?next=${encodeURIComponent(target)}`;
}

export default safeNext;
