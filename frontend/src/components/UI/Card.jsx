export default function Card({ className = '', children, ...props }) {
  return (
    <div className={`rounded-2xl border border-edge bg-panel p-4 ${className}`} {...props}>
      {children}
    </div>
  );
}
