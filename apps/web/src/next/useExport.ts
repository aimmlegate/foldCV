import { useEffect, useRef, useState, type RefObject } from "react";
import type { FieldEditorHandle } from "./FieldEditor";
import type { useEdits } from "./useEdits";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { RenderSnapshotV4 } from "../contracts/generated/render_snapshot_v4";
import { ApiFailure, docxDownload, projectRequest, type Workspace } from "./api";

type Operation = NonNullable<Workspace["project"]>["operations"][number];
type ExportState = { projectId: string; operation: Operation; snapshot: RenderSnapshotV4 | null };
export function useExport(workspace: Workspace | null, editor: RefObject<FieldEditorHandle | null>, edits: ReturnType<typeof useEdits>) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ExportState | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState("");
  const starting = useRef(false);
  const epoch = useRef(0);
  function accept(response: GuiProjectResponse, id: string) {
    const operation = response.workspace.project?.operations.find(item => item.id === id);
    if (!operation) throw new ApiFailure("INVALID_RESULT");
    setState({ projectId: response.workspace.projectId, operation,
      snapshot: response.workspace.project?.renders.find(item => item.id === operation.renderSnapshotId) ?? null });
  }
  async function start() {
    if (starting.current) return;
    starting.current = true;setMessage("");
    try {
      if (!await edits.flushBeforeAction()) throw new ApiFailure("PROJECT_SAVE_FAILED");
      await edits.acceptExternal(new Map(editor.current?.read().map(field => [field.fieldId, field.text]) ?? []));
      if (!await edits.flushBeforeAction()) throw new ApiFailure("PROJECT_SAVE_FAILED");
      const acknowledged = edits.acknowledged();
      if (!acknowledged?.project) return;
      const token = ++epoch.current;
      setOpen(true);setState(null);setBusy(true);
      const id = `export-${crypto.randomUUID()}`;
      const response = await projectRequest(`/v1/projects/${acknowledged.projectId}/exports`, "POST", {
        clientRequestId: id, projectRevision: acknowledged.projectRevision, documentRevision: acknowledged.documentRevision,
      });
      if (epoch.current === token) accept(response, id);
    } catch (error) {
      const unsaved = error instanceof ApiFailure && error.code === "PROJECT_SAVE_FAILED";
      setOpen(!unsaved);setMessage(unsaved ? "Завершите ввод и сохраните правки. Текст остаётся в редакторе."
        : "Не удалось сформировать DOCX. Текст доступен для правок и повтора.");
    }
    finally { starting.current = false;setBusy(false); }
  }
  useEffect(() => {
    if (!state || !["queued", "running"].includes(state.operation.status)) return;
    const token = epoch.current;
    const timer = window.setTimeout(() => {
      void projectRequest(`/v1/projects/${state.projectId}`).then(response => {
        if (token === epoch.current) accept(response, state.operation.id);
      }).catch(() => { if (token === epoch.current) setMessage("Не удалось проверить оформление. Текст доступен в редакторе."); });
    }, 250);
    return () => clearTimeout(timer);
  }, [state]);
  const current = !!state && workspace?.projectId === state.projectId
    && state.operation.baseRevision === workspace.projectRevision
    && state.operation.capturedDocumentRevision === workspace.documentRevision;
  async function download() {
    if (!state?.snapshot?.docx || !current || downloading) return;
    setDownloading(true);setMessage("");
    try {
      const blob = await docxDownload(`/v1/projects/${state.projectId}/exports/${state.operation.id}/docx`, state.snapshot.docx);
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url;link.download = "resume.docx";link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setMessage(error instanceof ApiFailure && error.code === "EXPORT_STALE"
      ? "Документ изменился. Сформируйте DOCX ещё раз."
      : "Не удалось скачать DOCX. Повторите скачивание; текст остаётся в редакторе."); }
    finally { setDownloading(false); }
  }
  async function cancel() {
    if (!state) return;
    try { accept(await projectRequest(`/v1/projects/${state.projectId}/operations/${state.operation.id}/cancel`, "POST", {}), state.operation.id); }
    catch { setMessage("Не удалось подтвердить остановку. Текст доступен в редакторе."); }
  }
  return { open, state, current, busy, downloading, message, start, download, cancel, close: () => setOpen(false) };
}
