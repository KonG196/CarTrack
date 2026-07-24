// Marque-logo URLs. Two sources, best-first:
//  1. Simple Icons (cdn.simpleicons.org/<slug>/white) — clean, normalised,
//     already-white monochrome marks that fill their box. Great where present.
//  2. car-logos-dataset thumb (jsDelivr) — full 387-brand coverage as a fallback
//     for the marques Simple Icons lacks (Mercedes-Benz, Dodge, Land Rover…).
//     Shown white via a CSS filter (see BrandLogo), so both sources match.
//
// The <BrandLogo> component tries #1 and falls back to #2 on error, so we never
// need to know per-brand which source has it.

const SIMPLE_ICONS = 'https://cdn.simpleicons.org';
const LOGO_THUMB =
  'https://cdn.jsdelivr.net/gh/filippofilip95/car-logos-dataset@master/logos/thumb';

// Hand-picked clean logos for marques whose car-logos entry is poor (has the
// brand name as text under the mark, or is tiny). These win over Simple Icons /
// the thumb. Whitened by the component's filter like the thumb. Keys are the
// car-logos slug (brandSlug output).
const LOGO_OVERRIDES = {
  // A clean 3-pointed star, no "Mercedes-Benz" wordmark under it (11KB SVG, PD).
  'mercedes-benz': 'https://upload.wikimedia.org/wikipedia/commons/3/32/Mercedes-Benz_Star_2022.svg',
};

// Post-Soviet marques written in Cyrillic → their Latin dataset slug.
const BRAND_ALIASES = {
  газ: 'gaz',
  заз: 'zaz',
  ваз: 'lada',
  лада: 'lada',
  уаз: 'uaz',
  зіл: 'zil',
  зил: 'zil',
  камаз: 'kamaz',
  москвич: 'moskvich',
  таврія: 'zaz',
};

// Our brand slug (car-logos convention: hyphenated). E.g. "Mercedes-Benz" →
// "mercedes-benz", "Alfa Romeo" → "alfa-romeo".
export function brandSlug(brand) {
  if (!brand || !brand.trim()) return null;
  const key = brand.trim().toLowerCase();
  if (BRAND_ALIASES[key]) return BRAND_ALIASES[key];
  const slug = key.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug || null;
}

// A hand-picked clean logo for this brand, if we have one. Whitened like the
// thumb (the source marks are dark). Wins over Simple Icons.
export function overrideLogoUrl(brand) {
  const slug = brandSlug(brand);
  return slug && LOGO_OVERRIDES[slug] ? LOGO_OVERRIDES[slug] : null;
}

// Simple Icons keys have no separators ("mercedesbenz"), so drop the hyphens.
export function simpleIconUrl(brand) {
  const slug = brandSlug(brand);
  if (!slug) return null;
  return `${SIMPLE_ICONS}/${slug.replace(/-/g, '')}/white`;
}

// The full-coverage colour thumbnail, whitened by the component's CSS filter.
export function thumbLogoUrl(brand) {
  const slug = brandSlug(brand);
  if (!slug) return null;
  return `${LOGO_THUMB}/${slug}.png`;
}

// Back-compat single-URL helper: the colour thumb (used where a plain <img>
// without the Simple-Icons fallback is fine).
export function brandLogoUrl(brand) {
  return thumbLogoUrl(brand);
}
