/** A shortcut as the system writes it: ⌘S on macOS, Ctrl+S on Windows. */
export function shortcut(key: string): string {
  const mac = typeof navigator !== "undefined" && /Macintosh|Mac OS X/u.test(navigator.userAgent);
  return mac ? `⌘${key}` : `Ctrl+${key}`;
}
