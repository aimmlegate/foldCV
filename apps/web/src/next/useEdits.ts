import { useEffect, useRef, useState, type RefObject } from "react";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { Mutation } from "../contracts/generated/mutation";
import type { DocumentPeriod } from "../contracts/generated/document";
import type { FieldEditorHandle } from "./FieldEditor";
import type { FieldProjection } from "./adapter";
import { ApiFailure, mutationRequest, projectRequest, type Workspace } from "./api";
import { documentFields } from "./fields";

type Pending = { field: FieldProjection; sessionId: string };
type Structural = Extract<Mutation, { kind: "add" | "delete" | "reorder" | "hide" }>;
export type StructuralIntent = Structural extends infer T ? T extends Structural ? Omit<T, "projectId" | "baseRevision" | "clientMutationId"> : never : never;
export function useEdits(workspace: Workspace | null, editor: RefObject<FieldEditorHandle | null>, accept: (response: GuiProjectResponse) => void) {
  const latest = useRef(workspace); latest.current = workspace;
  const acceptLatest = useRef(accept); acceptLatest.current = accept;
  const dirty = useRef(new Map<string, Pending>());
  const sessions = useRef(new Map<string, string>());
  const departed = useRef(new Set<string>());
  const queue = useRef(Promise.resolve());
  const failed = useRef<Mutation | null>(null);
  const terminal = useRef(false);
  const blocked = useRef(false);
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState("");

  function updatePending() { setPending(dirty.current.size > 0 || blocked.current); }
  function buffer(fields: FieldProjection[]) {
    const canonical = latest.current?.project?.document;
    if (!canonical) return;
    const saved = new Map(documentFields(canonical).map(field => [field.fieldId, field.text]));
    for (const field of fields) {
      if (saved.get(field.fieldId) === field.text) { dirty.current.delete(field.fieldId); continue; }
      let sessionId = sessions.current.get(field.slotId);
      if (!sessionId) { sessionId = crypto.randomUUID(); sessions.current.set(field.slotId, sessionId); }
      dirty.current.set(field.fieldId, { field, sessionId });
    }
    updatePending();
  }
  function enqueue(work: () => Promise<void>) {
    queue.current = queue.current.then(async () => {
      if (blocked.current) { setLocked(false); return; }
      setSaving(true);
      try { await work(); }
      catch (error) { blocked.current = true; setError(error instanceof ApiFailure && error.code === "MUTATION_STALE"
        ? "Текст на сервере изменился. Ваш ввод сохранён в окне; повторите сохранение после проверки."
        : "Не удалось сохранить правки. Ввод остаётся в окне; повторите сохранение."); }
      finally { setSaving(false); updatePending(); }
    });
    return queue.current;
  }
  function base() {
    const current = latest.current;
    if (!current) throw new ApiFailure("NO_DOCUMENT");
    return { projectId: current.projectId, baseRevision: current.documentRevision, clientMutationId: crypto.randomUUID() };
  }
  async function send(request: Mutation, sent = new Map<string, string>()) {
    const before = latest.current;
    failed.current = request;
    terminal.current = false;
    const result = await mutationRequest(request);
    const response = await projectRequest(`/v1/projects/${request.projectId}`);
    latest.current = response.workspace;
    acceptLatest.current(response);
    if (result.status === "stale" || result.status === "rejected" || result.rejectionReason !== null) {
      terminal.current = true;
      throw new ApiFailure("MUTATION_STALE");
    }
    const previous = new Map(before?.project ? documentFields(before.project.document).map(field => [field.fieldId, field.text]) : []);
    const live = new Map(editor.current?.read().map(field => [field.fieldId, field.text]) ?? []);
    if (response.workspace.project) {
      const patches = documentFields(response.workspace.project.document).filter(field => {
        const text = live.get(field.fieldId);
        return text !== undefined && text !== field.text && (text === sent.get(field.fieldId) || text === previous.get(field.fieldId));
      }).map(field => ({ fieldId: field.fieldId, text: field.text, capturedText: live.get(field.fieldId) ?? "" }));
      editor.current?.patch(patches);
    }
    for (const [id, text] of sent) if (dirty.current.get(id)?.field.text === text) dirty.current.delete(id);
    failed.current = null;
  }
  async function flush(slot?: string, completion: "none" | "slot" = "none") {
    const entries = [...dirty.current.values()].filter(item => slot === undefined || item.field.slotId === slot);
    for (const item of entries) {
      await send({ ...base(), kind: "edit-field", payload: { fieldId: item.field.fieldId, text: item.field.text,
        periods: null, focus: null, sessionId: item.sessionId, completion: "none" } }, new Map([[item.field.fieldId, item.field.text]]));
    }
    if (completion === "slot") {
      for (const [id, sessionId] of [...sessions.current]) {
        if (slot !== undefined && slot !== id) continue;
        const field = editor.current?.read().find(field => field.slotId === id);
        if (field) await send({ ...base(), kind: "edit-field", payload: { fieldId: field.fieldId, text: field.text,
          periods: null, focus: null, sessionId, completion: "slot" } }, new Map([[field.fieldId, field.text]]));
        sessions.current.delete(id);
      }
    }
  }
  useEffect(() => {
    const timer = window.setInterval(() => { if (dirty.current.size > 0 && !editor.current?.isComposing()) void enqueue(() => flush()); }, 1000);
    return () => clearInterval(timer);
  }, []);
  function departure(slot: string) {
    if (!sessions.current.has(slot)) return;
    departed.current.add(slot);
    void enqueue(async () => { await flush(slot, "slot"); departed.current.delete(slot); });
  }
  function restore(slot: string) {
    if (editor.current?.isComposing()) return;
    void enqueue(async () => {
      await flush(slot);
      const sent = new Map(editor.current?.read().filter(field => field.slotId === slot).map(field => [field.fieldId, field.text]) ?? []);
      await send({ ...base(), kind: "restore-previous-block", payload: { slotId: slot, sessionId: sessions.current.get(slot) ?? null } }, sent);
    });
  }
  function structural(intent: StructuralIntent) {
    if (blocked.current) return;
    if (editor.current?.isComposing()) { setError("Завершите ввод перед изменением разделов."); return; }
    setLocked(true);
    void enqueue(async () => { try { await flush(undefined, "slot"); await send({ ...base(), ...intent }); }
      finally { setLocked(false); } });
  }
  function periods(fieldId: string, update: (periods: DocumentPeriod[]) => DocumentPeriod[], slot: string) {
    if (blocked.current) return;
    if (editor.current?.isComposing()) return;
    setLocked(true);
    void enqueue(async () => { try {
      await flush(slot);
      let sessionId = sessions.current.get(slot);
      if (!sessionId) { sessionId = crypto.randomUUID(); sessions.current.set(slot, sessionId); }
      const job = latest.current?.project?.document.jobs.find(job => `job:${job.id}` === slot);
      if (!job) throw new ApiFailure("TARGET_NOT_FOUND");
      await send({ ...base(), kind: "edit-field", payload: { fieldId, text: null, periods: update(job.periods), focus: null, sessionId, completion: "field" } });
    } finally { setLocked(false); } });
  }
  function retry() {
    blocked.current = false; setError("");
    void enqueue(async () => {
      const request = failed.current;
      if (request) {
        const retried = terminal.current ? { ...request, ...base() } : request;
        const sent = request.kind === "edit-field" && request.payload.text !== null
          ? new Map([[request.payload.fieldId, request.payload.text]]) : new Map<string, string>();
        await send(retried, sent);
        if (request.kind === "edit-field" && request.payload.completion === "slot") {
          const document = latest.current?.project?.document;
          const slot = document && documentFields(document).find(field => field.fieldId === request.payload.fieldId)?.slotId;
          if (slot) sessions.current.delete(slot);
        }
      }
      await flush();
      for (const slot of [...departed.current]) { await flush(slot, "slot"); departed.current.delete(slot); }
    });
  }
  function completion(fieldId: string, reason: "field" | "paragraph") {
    const field = editor.current?.read().find(field => field.fieldId === fieldId);
    if (!field || !sessions.current.has(field.slotId)) return;
    void enqueue(async () => {
      await flush(field.slotId);
      const sessionId = sessions.current.get(field.slotId);
      const current = editor.current?.read().find(field => field.fieldId === fieldId);
      if (sessionId && current) await send({ ...base(), kind: "edit-field", payload: { fieldId, text: current.text,
        periods: null, focus: null, sessionId, completion: reason } }, new Map([[fieldId, current.text]]));
    });
  }
  function overlay(fields: FieldProjection[]) { return fields.map(field => ({ ...field, text: dirty.current.get(field.fieldId)?.field.text ?? field.text })); }
  return { buffer, departure, restore, structural, periods, retry, completion, overlay, pending, saving, locked, error };
}
