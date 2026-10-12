import { useRef, useState, type RefObject } from "react";
import type { Selection } from "../contracts/generated/selection";
import type { RulesSettings } from "../contracts/generated/rules_settings";
import type { FieldEditorHandle } from "./FieldEditor";
import type { useEdits } from "./useEdits";
import { ApiFailure, projectRequest, rewriteRequest, rulesRequest } from "./api";

type Target = { selection: Selection; fields: Map<string, string>; owner: string; rules: RulesSettings };
export function useRewrite(editor: RefObject<FieldEditorHandle | null>, edits: ReturnType<typeof useEdits>) {
  const [target, setTarget] = useState<Target | null>(null);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const active = useRef<{ projectId: string; operationId: string; cancelled: boolean } | null>(null);
  const opening = useRef(false);

  async function captureTarget(slot?: string) {
    setTarget(null);
    setMessage("");
    if (!await edits.flushBeforeAction()) { setMessage("Сначала завершите ввод и сохраните правки."); return; }
    const workspace = edits.acknowledged();
    if (!workspace?.project) return;
    const fields = editor.current?.read() ?? [];
    const spans = slot ? fields.filter(field => field.slotId === slot && field.text.length > 0)
      .map(field => ({ fieldId: field.fieldId, range: { start: 0, end: field.text.length }, capturedText: field.text }))
      : editor.current?.capture()?.spans ?? [];
    const first = spans[0];
    if (!first) { setMessage("Выделите текст для улучшения."); return; }
    const response = await projectRequest(`/v1/projects/${workspace.projectId}`);
    if (response.workspace.documentRevision !== workspace.documentRevision || !response.selectionFingerprint) {
      setMessage("Текст изменился. Выделите фрагмент снова."); return;
    }
    const selection: Selection = { projectId: workspace.projectId, documentRevision: workspace.documentRevision,
      dependencyFingerprint: response.selectionFingerprint, spans: [first, ...spans.slice(1)] };
    try {
      const rules = await rulesRequest();
      setTarget({ selection, fields: new Map(fields.map(field => [field.fieldId, field.text])),
        owner: fields.find(field => field.fieldId === spans.at(-1)?.fieldId)?.slotId ?? "profile", rules });
      setInstruction("");
    } catch { setMessage("Не удалось прочитать настройки текста. Повторите открытие помощника."); }
  }
  async function open(slot?: string) {
    if (opening.current || active.current) return;
    opening.current = true;
    try { await captureTarget(slot); }
    catch { setMessage("Не удалось открыть помощник. Текст остаётся в документе."); }
    finally { opening.current = false; }
  }
  function invalidate() {
    const operation = active.current;
    if (!operation || operation.cancelled) return;
    operation.cancelled = true;
    void projectRequest(`/v1/projects/${operation.projectId}/operations/${operation.operationId}/cancel`, "POST", {})
      .catch(() => { setMessage("Не удалось подтвердить остановку. Новые правки остаются в документе."); });
  }
  async function submit() {
    if (!target || busy || !instruction.trim()) return;
    if (!await edits.flushBeforeAction()) { setMessage("Сначала сохраните правки."); return; }
    const current = edits.acknowledged();
    if (current?.projectId !== target.selection.projectId || current.documentRevision !== target.selection.documentRevision) {
      setMessage("Текст изменился. Выделите фрагмент снова."); return;
    }
    const operation = { projectId: current.projectId, operationId: `rewrite-${crypto.randomUUID()}`, cancelled: false };
    active.current = operation; setBusy(true); setMessage("");
    try {
      const result = await rewriteRequest({ clientRequestId: operation.operationId, selection: target.selection,
        instruction: instruction.trim(), rulesRevision: target.rules.revision, rulesSha256: target.rules.sha256 });
      await edits.acceptExternal(target.fields);
      if (result.status !== "applied" || result.rejectionReason !== null) throw new ApiFailure(result.rejectionReason ?? "REWRITE_FAILED");
      setMessage(result.persistence === "durable" ? "Текст обновлён. Предыдущая версия сохранена для каждого изменённого блока."
        : "Текст обновлён, но запись на диск не подтверждена. Повторите сохранение.");
      setTarget(null);
    } catch (error) {
      setMessage(error instanceof ApiFailure && error.code === "CANCELLED" ? "Улучшение отменено. Ваши правки сохранены."
        : "Не удалось обновить выделение. Текст и ваши правки сохранены; выделите фрагмент для повтора.");
    } finally { if (active.current === operation) active.current = null; setBusy(false); }
  }
  return { target, instruction, setInstruction, busy, message, invalidate,
    open, submit, close: () => setTarget(null) };
}
