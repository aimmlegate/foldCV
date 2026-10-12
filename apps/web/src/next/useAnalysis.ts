import { useEffect, useRef, useState } from "react";
import { analysisRequest, preferencesRequest, type Workspace } from "./api";
import type { useEdits } from "./useEdits";

export function useAnalysis(workspace: Workspace | null, edits: ReturnType<typeof useEdits>) {
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState("");
  const current = useRef(edits);current.current = edits;
  const operations = workspace?.project?.operations ?? [];
  const pending = [...operations].reverse().find(operation => operation.kind === "reconcile_edits" && operation.status === "queued" && operation.analysisBatch?.phase === "pending");
  const running = operations.some(operation => operation.kind === "reconcile_edits" && ["queued", "running"].includes(operation.status) && operation.analysisBatch?.phase === "dispatched");
  const polling = running || (enabled && pending?.analysisBatch?.enabled === true && pending.analysisBatch.completedFieldIds.length > 0);
  useEffect(() => {
    void preferencesRequest().then(value => setEnabled(value.automaticAnalysis)).catch(() => setError("Не удалось прочитать настройку проверки изменений."));
  }, []);
  useEffect(() => {
    if (!workspace || !polling) return;
    let alive = true;
    const timer = window.setTimeout(() => {
      if (alive) void current.current.acceptExternal(new Map()).catch(() => setError("Не удалось прочитать состояние проверки."));
    }, 400);
    return () => { alive = false;clearTimeout(timer); };
  }, [workspace, polling]);
  async function retry() {
    if (!await current.current.flushBeforeAction()) { setError("Сначала сохраните правки.");return; }
    const id = current.current.acknowledged()?.projectId;
    if (!id) return;
    try { await analysisRequest(id, "retry");await current.current.acceptExternal(new Map());setError(""); }
    catch { setError("Не удалось запустить проверку. Повторите действие."); }
  }
  function preferenceChanged(value: boolean) {
    setEnabled(value);void current.current.acceptExternal(new Map()).catch(() => setError("Не удалось прочитать состояние проверки."));
  }
  const message = running ? "Проверяем изменения" : pending ? !enabled ? "Проверка изменений приостановлена"
    : pending.errorCode ? "Не удалось проверить изменения. Правки сохранены в редакторе."
    : pending.analysisBatch?.completedFieldIds.length ? "Проверка изменений ожидает запуска" : "Проверим после завершения правки" : "";
  return { message, error, retry, preferenceChanged, retryable: enabled && !!pending?.errorCode };
}
