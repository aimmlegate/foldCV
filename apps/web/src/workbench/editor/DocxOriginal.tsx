import { useEffect, useRef, useState } from "react";
import { OperationStatus } from "../ui/OperationStatus";
import { markDom, unshownStyle, type Unshown } from "./unshown";

const frameHtml = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data: blob:;"><style>body{margin:0;background:var(--source-desk)} .docx-wrapper{padding:24px!important;background:transparent!important} .docx-wrapper>section.docx{margin:0 auto 24px!important;box-shadow:none!important}</style></head><body></body></html>`;

export function DocxOriginal({ blob, unshown }: { blob: Blob; unshown: readonly Unshown[] }) {
  // The lines as one value: a new list of the same lines must not draw the file again.
  const lines = JSON.stringify(unshown);
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false), [error, setError] = useState(false), [generation, setGeneration] = useState(0);
  useEffect(() => {
    const target = frame.current?.contentDocument;
    if (!target || !generation) return;
    let active = true;
    const body = target.createElement("div"), styles = target.createElement("div"), marks = target.createElement("style");
    marks.textContent = unshownStyle;
    target.body.replaceChildren(marks, styles, body);
    if (frame.current) target.documentElement.style.setProperty("--source-desk", getComputedStyle(frame.current).getPropertyValue("--desk"));
    const fit = () => {
      const width = frame.current?.clientWidth ?? 0;
      const pages = Array.from(body.querySelectorAll<HTMLElement>("section.docx"));
      const pageWidth = Math.max(0, ...pages.map(page => page.offsetWidth));
      if (!width || !pageWidth) return;
      const zoom = Math.min(1, Math.max(0.1, (width - 48) / pageWidth));
      for (const page of pages) page.style.zoom = String(zoom);
    };
    const observer = new ResizeObserver(fit);
    if (frame.current) observer.observe(frame.current);
    const preventNavigation = (event: MouseEvent) => { event.preventDefault(); };
    target.addEventListener("click", preventNavigation);
    setReady(false); setError(false);
    void import("docx-preview").then(async ({ renderAsync }) => {
      if (!active) return;
      await renderAsync(blob, body, styles, { useBase64URL: true, renderAltChunks: false,
        ignoreLastRenderedPageBreak: false, renderHeaders: true, renderFooters: true });
      // The lines the resume does not show, marked in the drawn text.
      if (active) { markDom(body, JSON.parse(lines) as Unshown[]); fit(); setReady(true); }
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; observer.disconnect(); target.removeEventListener("click", preventNavigation); body.remove(); styles.remove(); marks.remove(); };
  }, [blob, generation, lines]);
  return <>
    <p className="source-viewer-note">В Word вид может отличаться.</p>
    {error ? <p className="source-viewer-message" role="alert">Не удалось показать DOCX. Скачайте оригинал.</p>
      : !ready && <div className="source-render-status"><OperationStatus label="Показываем DOCX" timed /></div>}
    <iframe ref={frame} className="source-preview-frame" title="Оригинал DOCX" sandbox="allow-same-origin" srcDoc={frameHtml}
      hidden={error} onLoad={() => setGeneration(value => value + 1)} />
  </>;
}
