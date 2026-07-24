import useCarImage from '../hooks/useCarImage';

// A small thumbnail of the car (photo, else marque logo, else nothing). Kept for
// places that want the car picture inline; the dashboard header uses the
// photo-as-background treatment instead (see Dashboard).
export default function CarPhoto({ carId, className = '' }) {
  const { data, failed, setFailed } = useCarImage(carId);

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
