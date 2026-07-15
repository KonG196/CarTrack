const SIZES = {
  sm: 'text-sm',
  lg: 'text-2xl',
};

export default function Wordmark({ size = 'sm', className = '' }) {
  return (
    <span
      className={`whitespace-nowrap font-display font-semibold tracking-[0.02em] text-fg ${SIZES[size] || SIZES.sm} ${className}`}
    >
      KAPOT <span className="text-amber">TRACKER</span>
    </span>
  );
}
