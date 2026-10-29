export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`operation-spinner ${className}`} aria-hidden="true" />;
}
