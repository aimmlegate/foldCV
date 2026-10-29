import { errorMessage } from "../../errors/messages";
import { lazy, Suspense, useEffect, useState } from "react";
import { loadOriginal, originalKind, originalUrl } from "./original-source";
import { DocxOriginal } from "./DocxOriginal";
import { TextOriginal } from "./TextOriginal";
import { OperationStatus } from "../ui/OperationStatus";

const PdfOriginal = lazy(() => import("./PdfOriginal"));

type Loaded = { blob: Blob; text: string };

export function OriginalPreview({ projectId, source }: {
  projectId: string; source: { id: string; originalName: string; byteSha256: string };
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null), [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const kind = originalKind(source.originalName);
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(null); setError("");
    void loadOriginal(originalUrl(projectId, source.id), source.byteSha256, controller.signal).then(async blob => {
      const text = kind === "text" || kind === "markdown" ? new TextDecoder("utf-8", { fatal: true }).decode(await blob.arrayBuffer()) : "";
      if (controller.signal.aborted) return;
      setLoaded({ blob, text });
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Не удалось открыть оригинал.");
    });
    return () => controller.abort();
  }, [projectId, source.id, source.byteSha256, kind, attempt]);
  if (error) return <div className="source-viewer-message" role="alert">{errorMessage(error)}<button className="text-button" onClick={() => setAttempt(value => value + 1)}>Повторить</button></div>;
  if (!loaded) return <div className="source-viewer-message"><OperationStatus label="Открываем оригинал" timed /></div>;
  if (kind === "pdf") return <Suspense fallback={<div className="source-viewer-message"><OperationStatus label="Открываем PDF" timed /></div>}><PdfOriginal blob={loaded.blob} /></Suspense>;
  if (kind === "docx") return <DocxOriginal blob={loaded.blob} />;
  if (kind === "text" || kind === "markdown") return <TextOriginal text={loaded.text} markdown={kind === "markdown"} />;
  return <p className="source-viewer-message">Этот формат можно только скачать.</p>;
}
