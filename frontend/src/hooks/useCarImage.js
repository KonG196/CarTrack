import { useEffect, useState } from 'react';
import { getCarImage } from '../api/cars';

// Shared fetch for a car's imagery: { url, logo } (either may be null), plus a
// `failed` flag if an <img> for it errors. Both CarPhoto (thumbnail) and the
// dashboard header-background use it, so the endpoint is hit once per mount.
export default function useCarImage(carId) {
  const [data, setData] = useState(null); // { url, logo } | null while loading
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

  return { data, failed, setFailed };
}
