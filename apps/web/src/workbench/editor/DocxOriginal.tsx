import { useEffect, useRef, useState } from "react";
import { OperationStatus } from "../ui/OperationStatus";

const frameHtml = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data: blob:;"><style>body{margin:0;background:var(--source-desk)} .docx-wrapper{padding:24px!important;background:transparent!important} .docx-wrapper>section.docx{margin:0 auto 24px!important;box-shadow:none!important}</style></head><body></body></html>`;

export function DocxOriginal({ blob }: { blob: Blob }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false), [error, setError] = useState(false), [generation, setGeneration] = useState(0);
  useEffect(() => {
    const target = frame.current?.contentDocument;
    if (!target || !generation) return;
    let active = true;
    const body = target.createElement("div"), styles = target.createElement("div");
    target.body.replaceChildren(styles, body);
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
      if (active) { fit(); setReady(true); }
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; observer.disconnect(); target.removeEventListener("click", preventNavigation); body.remove(); styles.remove(); };
  }, [blob, generation]);
  return <>
    <p className="source-viewer-note">Предпросмотр DOCX. Шрифты и расположение элементов могут отличаться от Word.</p>
    {error ? <p className="source-viewer-message" role="alert">Не удалось показать DOCX. Скачайте оригинал и откройте в Word.</p>
      : !ready && <div className="source-render-status"><OperationStatus label="Отрисовываем DOCX" timed /></div>}
    <iframe ref={frame} className="source-preview-frame" title="Оригинал DOCX" sandbox="allow-same-origin" srcDoc={frameHtml}
      hidden={error} onLoad={() => setGeneration(value => value + 1)} />
  </>;
}
