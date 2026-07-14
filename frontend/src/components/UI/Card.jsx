export default function Card({ className = '', children, ...props }) {
  return (
    <div
      className={`rounded-2xl border border-slate-800 bg-slate-900 p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
