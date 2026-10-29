import { errorMessage } from "../../errors/messages";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, type PDFPageProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { OperationStatus } from "../ui/OperationStatus";

GlobalWorkerOptions.workerSrc = workerUrl;

// Zoom and resizes scale the pages but not the gaps, so the scroll spot is kept as a page and a place on it.
type Anchor = { page: number; fraction: number; gap: number };

function locate(root: HTMLElement): { anchor: Anchor; current: number } | null {
  const top = root.getBoundingClientRect().top, middle = top + root.clientHeight / 2;
  const boxes = Array.from(root.querySelectorAll("[data-page]"), page => page.getBoundingClientRect());
  const first = boxes.findIndex(box => box.bottom > top), center = boxes.findIndex(box => box.bottom > middle);
  const index = first < 0 ? boxes.length - 1 : first, box = boxes[index];
  if (!box || !root.clientHeight) return null;
  const offset = top - box.top;
  return { anchor: { page: index, fraction: box.height ? Math.max(0, offset) / box.height : 0, gap: Math.min(0, offset) },
    current: center < 0 ? boxes.length : center + 1 };
}

function clear(host: HTMLElement) {
  for (const canvas of host.querySelectorAll("canvas")) { canvas.width = 0; canvas.height = 0; }
  host.replaceChildren();
}

function PdfPage({ page, total, width, near }: { page: PDFPageProxy; total: number; width: number; near: boolean }) {
  const host = useRef<HTMLDivElement>(null), [shown, setShown] = useState(false), [failed, setFailed] = useState(false);
  const scale = width / page.getViewport({ scale: 1 }).width, size = page.getViewport({ scale });
  useEffect(() => {
    const container = host.current;
    if (!container) return;
    if (!near) { clear(container); setShown(false); return; }
    let active = true, done = false;
    const viewport = page.getViewport({ scale }), canvas = document.createElement("canvas");
    const density = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(16_000_000 / (viewport.width * viewport.height)));
    canvas.width = Math.ceil(viewport.width * density); canvas.height = Math.ceil(viewport.height * density);
    canvas.setAttribute("aria-label", `Страница ${page.pageNumber} из ${total}`);
    canvas.setAttribute("role", "img");
    const render = page.render({ canvas, viewport, transform: [density, 0, 0, density, 0, 0] });
    void render.promise.then(() => {
      done = true;
      if (active) { clear(container); container.append(canvas); setShown(true); setFailed(false); }
    }, () => { done = true; if (active) { clear(container); setFailed(true); } });
    // The shown canvas stays, stretched to the new size, until the next render replaces it.
    return () => { active = false; if (!done) render.cancel(); if (!canvas.isConnected) { canvas.width = 0; canvas.height = 0; } };
  }, [page, scale, near, total]);
  return <div className="source-pdf-page" data-page={page.pageNumber} style={{ width: size.width, height: size.height }}>
    <div ref={host} className="source-pdf-canvas" />
    {failed ? <p className="source-viewer-message" role="alert">Не удалось показать страницу {page.pageNumber}. Скачайте оригинал.</p>
      : near && !shown && <div className="source-render-status"><OperationStatus label={`Показываем страницу ${page.pageNumber}`} /></div>}
  </div>;
}

export default function PdfOriginal({ blob }: { blob: Blob }) {
  const [pages, setPages] = useState<PDFPageProxy[]>([]), [near, setNear] = useState<ReadonlySet<number>>(() => new Set());
  const [zoom, setZoom] = useState(1), [width, setWidth] = useState(0), [current, setCurrent] = useState(1), [error, setError] = useState("");
  const scroll = useRef<HTMLDivElement>(null), anchor = useRef<Anchor | null>(null), restored = useRef(-1), measured = width > 0;
  useEffect(() => {
    let active = true;
    const assets = new URL("pdfjs/6.4.299/", document.baseURI).href;
    const url = URL.createObjectURL(blob);
    const task = getDocument({ url, cMapUrl: `${assets}cmaps/`, cMapPacked: true,
      standardFontDataUrl: `${assets}standard_fonts/`, wasmUrl: `${assets}wasm/`, iccUrl: `${assets}iccs/` });
    void task.promise.then(pdf => Promise.all(Array.from({ length: pdf.numPages }, (_, index) => pdf.getPage(index + 1))))
      .then(result => { if (active) setPages(result); }).catch((cause: unknown) => {
        if (active) setError(cause instanceof Error && cause.name === "PasswordException"
          ? "PDF защищён паролем. Скачайте оригинал." : "Не удалось показать PDF. Скачайте оригинал.");
      });
    return () => { active = false; void task.destroy(); URL.revokeObjectURL(url); };
  }, [blob]);
  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const observer = new ResizeObserver(() => { if (element.clientWidth) setWidth(Math.max(1, element.clientWidth - 48)); });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const root = scroll.current;
    if (!root || !measured || !pages.length) return;
    // Only pages within a screen of the view keep a canvas; a hidden pane keeps what it has.
    const observer = new IntersectionObserver(entries => {
      if (root.clientHeight) setNear(previous => {
        const next = new Set(previous);
        for (const entry of entries) {
          const number = Number(entry.target.getAttribute("data-page"));
          if (entry.isIntersecting) next.add(number); else next.delete(number);
        }
        return next;
      });
    }, { root, rootMargin: "100% 0px" });
    for (const page of root.querySelectorAll("[data-page]")) observer.observe(page);
    return () => observer.disconnect();
  }, [pages, measured]);
  function track() {
    const root = scroll.current, found = root && locate(root);
    if (!root || !found) return;
    setCurrent(found.current);
    // A scroll made by the restore below keeps the anchor, so rounding does not drift during a divider drag.
    if (root.scrollTop === restored.current) return;
    restored.current = -1; anchor.current = found.anchor;
  }
  useLayoutEffect(() => {
    const root = scroll.current, saved = anchor.current, page = saved && root?.querySelectorAll("[data-page]").item(saved.page);
    if (root && saved && page) {
      const box = page.getBoundingClientRect();
      root.scrollTop += box.top - root.getBoundingClientRect().top + saved.fraction * box.height + saved.gap;
      restored.current = root.scrollTop;
    }
    track();
  }, [width, zoom]);
  return <>
    <div className="source-pdf-controls" aria-label="Просмотр PDF">
      <span>{pages.length ? `${current} / ${pages.length}` : "PDF"}</span>
      <select aria-label="Масштаб" value={zoom} onChange={event => setZoom(Number(event.currentTarget.value))}>
        <option value={1}>По ширине</option><option value={1.5}>150%</option><option value={2}>200%</option>
      </select>
    </div>
    {error && <p className="source-viewer-message" role="alert">{errorMessage(error)}</p>}
    <div ref={scroll} className="source-pdf-scroll" onScroll={track}>
      {!error && !pages.length && <div className="source-render-status"><OperationStatus label="Читаем PDF" /></div>}
      {measured && pages.map(page => <PdfPage key={page.pageNumber} page={page} total={pages.length} width={width * zoom}
        near={near.has(page.pageNumber)} />)}
    </div>
  </>;
}
