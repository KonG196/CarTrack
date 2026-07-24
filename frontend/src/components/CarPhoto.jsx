import { useEffect, useState } from 'react';
import { getCarImage } from '../api/cars';

// The car's picture beside its name: a real CC0 photo (Wikimedia) when one
// exists, otherwise the marque logo, otherwise nothing (no box, no broken image,
// no layout shift). The endpoint returns {url, logo}; a photo fills the frame
// (object-cover), a logo sits contained with padding so it reads as a badge.
export default function CarPhoto({ carId, className = '' }) {
  const [data, setData] = useState(null); // { url, logo }
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setFailed(false);
    getCarImage(carId)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [carId]);

  if (failed || !data) return null;
  const src = data.url || data.logo;
  if (!src) return null;

  const isLogo = !data.url && data.logo;
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className={`h-12 w-16 flex-shrink-0 rounded-lg ${
        isLogo ? 'bg-panel object-contain p-1.5' : 'object-cover'
      } ${className}`}
    />
  );
}
