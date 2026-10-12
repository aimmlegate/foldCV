import { useRef, useState, type RefObject } from "react";
import type { FieldEditorHandle } from "./FieldEditor";
import type { RelatedUpdateSuggestion } from "../contracts/generated/workspace_v5";
import type { Mutation } from "../contracts/generated/mutation";
import type { useEdits } from "./useEdits";
import { ApiFailure, mutationRequest, projectRequest } from "./api";

type Intent = { request: Extract<Mutation, { kind: "apply-related-update" }>; fields: Map<string, string> };
export function useRelated(editor: RefObject<FieldEditorHandle | null>, edits: ReturnType<typeof useEdits>) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const pending = useRef<Intent | null>(null);
  const starting = useRef(false);
  async function send(intent: Intent) {
    setBusy(true);setMessage("");
    try {
      const result = await mutationRequest(intent.request);
      await edits.acceptExternal(intent.fields);
      if (!["applied", "replayed"].includes(result.status) || result.rejectionReason !== null) {
        pending.current = null;throw new ApiFailure(result.rejectionReason ?? "RELATED_UPDATE_STALE");
      }
      pending.current = null;
      setMessage(result.persistence === "durable" ? result.status === "replayed" ? "Это действие уже выполнено."
        : result.changedSlotIds.length === 0 ? "Текст уже соответствует предложению." : "Связанный текст обновлён. Предыдущая версия блока сохранена."
        : "Текст обновлён, но запись на диск не подтверждена. Повторите сохранение.");
    } catch (error) {
      setMessage(error instanceof ApiFailure && ["RELATED_UPDATE_STALE", "MUTATION_STALE", "DOCUMENT_REVISION_CHANGED"].includes(error.code)
        ? "Предложение устарело. Новые правки остаются в документе; завершите их и дождитесь проверки."
        : "Не удалось подтвердить обновление. Ваши правки остаются в редакторе.");
    } finally { setBusy(false); }
  }
  async function apply(suggestion: RelatedUpdateSuggestion) {
    if (busy || starting.current) return;
    starting.current = true;setBusy(true);
    try {
      if (!await edits.flushBeforeAction()) { setMessage("Сначала завершите ввод и сохраните правки.");return; }
      const current = edits.acknowledged();
      if (!current) return;
      const fields = new Map(editor.current?.read().map(field => [field.fieldId, field.text]) ?? []);
      const response = await projectRequest(`/v1/projects/${current.projectId}`);
      if (response.workspace.projectRevision !== suggestion.dependencies.projectRevision || response.workspace.documentRevision !== suggestion.dependencies.documentRevision) {
        setMessage("Предложение устарело. Завершите правку и дождитесь проверки.");await edits.acceptExternal(new Map());return;
      }
      const intent: Intent = { request: { kind: "apply-related-update", projectId: current.projectId,
        clientMutationId: crypto.randomUUID(), baseRevision: current.documentRevision,
        payload: { suggestionId: suggestion.id, dependencies: suggestion.dependencies } },
        fields };
      pending.current = intent;await send(intent);
    } catch { setMessage("Не удалось прочитать предложение. Повторите действие после сохранения правок."); }
    finally { starting.current = false;setBusy(false); }
  }
  async function retry() {
    const intent = pending.current;
    if (!intent || busy || !await edits.flushBeforeAction()) return;
    await send(intent);
  }
  return { busy, message, apply, retry, retryable: pending.current !== null && !busy };
}
