import useCarImage from '../hooks/useCarImage';

// The dashboard's car block. When a real photo exists it becomes the darkened
// BACKGROUND of the block (the user asked for this — far more visible than a
// thumbnail, with a gradient keeping the name/odometer readable on top). With
// only a marque logo, that logo sits as a small badge on the left of a plain
// block; with nothing, it's just a plain block. Either way `children` (the name
// row + odometer control) render on top unchanged.
export default function CarHeaderCard({ carId, children }) {
  const { data, failed, setFailed } = useCarImage(carId);
  const photo = !failed && data?.url ? data.url : null;
  const logo = !failed && !photo && data?.logo ? data.logo : null;

  if (photo) {
    return (
      <div className="relative overflow-hidden rounded-2xl border border-edge">
        <img
          src={photo}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover object-right"
        />
        {/* An even, mostly-uniform darkening so text stays legible without one
            side looking far heavier than the other: a flat veil across the whole
            photo, plus a gentle bottom-up lift under the tiles. */}
        <div className="absolute inset-0 bg-garage/70" />
        <div className="absolute inset-0 bg-gradient-to-t from-garage/50 to-transparent" />
        <div className="relative p-4">{children}</div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 px-1">
      {logo ? (
        <img
          src={logo}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-12 w-16 flex-shrink-0 rounded-lg bg-panel object-contain p-1.5"
        />
      ) : null}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
