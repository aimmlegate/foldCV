import { errorMessage } from "../../errors/messages";
import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { OperationStatus } from "../ui/OperationStatus";

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfOriginal({ blob }: { blob: Blob }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null), [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1), [width, setWidth] = useState(0), [error, setError] = useState("");
  const [rendering, setRendering] = useState(true);
  const scroll = useRef<HTMLDivElement>(null), host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    const assets = new URL("pdfjs/6.4.299/", document.baseURI).href;
    const url = URL.createObjectURL(blob);
    const task = getDocument({ url, cMapUrl: `${assets}cmaps/`, cMapPacked: true,
      standardFontDataUrl: `${assets}standard_fonts/`, wasmUrl: `${assets}wasm/`, iccUrl: `${assets}iccs/` });
    void task.promise.then(result => { if (active) setPdf(result); }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error && cause.name === "PasswordException"
        ? "PDF защищён паролем. Скачайте оригинал для просмотра." : "Не удалось показать PDF. Скачайте оригинал для просмотра.");
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
    scroll.current?.scrollTo(0, 0);
  }, [page]);
  useEffect(() => {
    const container = host.current;
    if (!pdf || !container || !width) return;
    let active = true, render: RenderTask | undefined;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-label", `Страница ${page} из ${pdf.numPages}`);
    canvas.setAttribute("role", "img");
    container.replaceChildren(); setRendering(true); setError("");
    void pdf.getPage(page).then(async documentPage => {
      if (!active) return;
      const natural = documentPage.getViewport({ scale: 1 });
      const viewport = documentPage.getViewport({ scale: width / natural.width * zoom });
      const density = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(16_000_000 / (viewport.width * viewport.height)));
      canvas.width = Math.ceil(viewport.width * density); canvas.height = Math.ceil(viewport.height * density);
      canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
      render = documentPage.render({ canvas, viewport, transform: [density, 0, 0, density, 0, 0] });
      await render.promise;
      if (active) { container.replaceChildren(canvas); setRendering(false); }
    }).catch(() => { if (active) { setError("Не удалось отрисовать страницу PDF. Скачайте оригинал для просмотра."); setRendering(false); } });
    return () => { active = false; render?.cancel(); canvas.width = 0; canvas.height = 0; };
  }, [pdf, page, zoom, width]);
  return <>
    <div className="source-pdf-controls" aria-label="Просмотр PDF">
      <button className="text-button" disabled={!pdf || page <= 1} onClick={() => setPage(value => value - 1)}>Назад</button>
      <span>{pdf ? `${page} / ${pdf.numPages}` : "PDF"}</span>
      <button className="text-button" disabled={!pdf || page >= pdf.numPages} onClick={() => setPage(value => value + 1)}>Далее</button>
      <select aria-label="Масштаб оригинала" value={zoom} onChange={event => setZoom(Number(event.currentTarget.value))}>
        <option value={1}>По ширине</option><option value={1.5}>150%</option><option value={2}>200%</option>
      </select>
    </div>
    {error && <p className="source-viewer-message" role="alert">{errorMessage(error)}</p>}
    <div ref={scroll} className="source-pdf-scroll">
      {!error && rendering && <div className="source-render-status"><OperationStatus label={pdf ? `Отрисовываем страницу ${page}` : "Читаем PDF"} /></div>}
      <div ref={host} />
    </div>
  </>;
}
