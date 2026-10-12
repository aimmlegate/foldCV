import { useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";
const key = "foldcv-theme";
function storedMode(): ThemeMode { const value = localStorage.getItem(key); return value === "light" || value === "dark" ? value : "system"; }
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(storedMode);
  const [resolved, setResolved] = useState<"light" | "dark">(() => document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const next = mode === "system" ? media.matches ? "dark" : "light" : mode;
      document.documentElement.dataset.theme = next; setResolved(next);
    };
    apply(); media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);
  return { mode, resolved, select: (value: string) => {
    if (value !== "light" && value !== "dark" && value !== "system") return;
    if (value === "system") localStorage.removeItem(key); else localStorage.setItem(key, value);
    setMode(value);
  } };
}
