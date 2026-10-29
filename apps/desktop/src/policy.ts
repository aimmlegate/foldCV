/** The window shows only pages of its own service. */
export function appUrl(raw: string, origin: string): boolean {
  try { return new URL(raw).origin === origin; } catch { return false; }
}

/** A link for the default browser or mail app; anything else is dropped. */
export function externalUrl(raw: string): string | null {
  try {
    const url = new URL(raw);
    return ["https:", "http:", "mailto:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
