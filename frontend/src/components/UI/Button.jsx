const VARIANTS = {
  primary:
    'bg-amber text-amber-ink hover:bg-amber-deep active:bg-amber-deep disabled:bg-edge disabled:text-mist',
  secondary:
    'border border-edge bg-panel text-fg hover:bg-raised active:bg-raised disabled:text-mist',
  danger:
    'border border-crit/40 bg-crit/10 text-crit hover:bg-crit/20 disabled:border-edge disabled:text-mist',
  ghost: 'text-mist hover:bg-panel hover:text-fg disabled:text-edge',
};

export default function Button({
  variant = 'primary',
  className = '',
  type = 'button',
  children,
  ...props
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
