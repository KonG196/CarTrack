import { useEffect, useState } from 'react';
import { overrideLogoUrl, simpleIconUrl, thumbLogoUrl } from '../utils/carLogo';

// A white marque logo that fills its box. Sources, best-first:
//  1. a hand-picked override (clean, no wordmark) for marques whose dataset logo
//     is poor — e.g. a bare Mercedes star. Whitened by CSS.
//  2. Simple Icons — clean white monochrome marks that fill their box.
//  3. the full-coverage colour thumbnail, whitened by CSS.
// Falls forward on <img> error; renders nothing if none resolve.
export default function BrandLogo({ brand, className = 'h-6 w-6' }) {
  const override = overrideLogoUrl(brand);
  const si = simpleIconUrl(brand);
  const thumb = thumbLogoUrl(brand);

  // The ordered candidates: [url, needsWhitening]. Simple Icons is already white.
  const chain = [
    override ? [override, true] : null,
    si ? [si, false] : null,
    thumb ? [thumb, true] : null,
  ].filter(Boolean);

  const [i, setI] = useState(0);

  // Reset when the brand (hence the chain) changes.
  useEffect(() => {
    setI(0);
  }, [override, si, thumb]);

  if (i >= chain.length) return null;
  const [src, whiten] = chain[i];

  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setI((n) => n + 1)}
      className={`${className} flex-shrink-0 object-contain ${
        whiten ? '[filter:brightness(0)_invert(1)]' : ''
      }`}
    />
  );
}
