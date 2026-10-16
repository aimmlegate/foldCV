export function validLink(href: string): boolean {
  if (/\s/.test(href)) return false;
  try { const url = new URL(href); return (url.protocol === "https:" || url.protocol === "http:") && url.hostname.length > 0
    || url.protocol === "mailto:" && url.pathname.length > 0; } catch { return false; }
}
