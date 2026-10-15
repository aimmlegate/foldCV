import type { ButtonHTMLAttributes } from "react";

export function Button({ variant = "default", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "quiet" | "danger";
}) {
  const variants = { default: "button", primary: "button primary", quiet: "button quiet", danger: "button danger" };
  return <button type="button" className={`${variants[variant]} ${className}`} {...props} />;
}
