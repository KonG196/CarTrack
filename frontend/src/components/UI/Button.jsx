const VARIANTS = {
  primary:
    'bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white disabled:bg-slate-700 disabled:text-slate-400',
  secondary:
    'bg-slate-800 hover:bg-slate-700 active:bg-slate-800 text-slate-100 border border-slate-700 disabled:text-slate-500',
  danger:
    'bg-red-600/10 hover:bg-red-600/20 text-red-400 border border-red-900/60 disabled:text-slate-500',
  ghost: 'bg-transparent hover:bg-slate-800 text-slate-300 disabled:text-slate-600',
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
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
