import type { ButtonHTMLAttributes } from "react";
import { Spinner } from "./OperationStatus";

export function Button({ variant = "default", className = "", busy = false, busyLabel = "Подождите…", children, disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "quiet" | "danger";
  busy?: boolean; busyLabel?: string;
}) {
  const variants = { default: "button", primary: "button primary", quiet: "button quiet", danger: "button danger" };
  return <button type="button" className={`${variants[variant]} ${className}`} disabled={disabled || busy} aria-busy={busy} {...props}>
    <span className="button-content" aria-hidden={busy || undefined}>{children}</span>
    {busy && <span className="button-progress" role="status"><Spinner /><span>{busyLabel}</span></span>}
  </button>;
}
