import { useEffect, useRef, useState, type RefObject } from "react";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { Mutation } from "../contracts/generated/mutation";
import type { DocumentPeriod } from "../contracts/generated/document";
import type { FieldEditorHandle } from "./FieldEditor";
import type { FieldProjection } from "./adapter";
import { ApiFailure, analysisRequest, mutationRequest, projectRequest, type Workspace } from "./api";
import { documentFields } from "./fields";

type Pending = { field: FieldProjection; sessionId: string; since: number };
type Structural = Extract<Mutation, { kind: "add" | "delete" | "reorder" | "hide" }>;
export type StructuralIntent = Structural extends infer T ? T extends Structural ? Omit<T, "projectId" | "baseRevision" | "clientMutationId"> : never : never;
export function useEdits(workspace: Workspace | null, editor: RefObject<FieldEditorHandle | null>, accept: (response: GuiProjectResponse) => void) {
  const latest = useRef(workspace); latest.current = workspace;
  const acceptLatest = useRef(accept); acceptLatest.current = accept;
  const dirty = useRef(new Map<string, Pending>());
  const invalidated = useRef(new Set<string>());
  const sessions = useRef(new Map<string, string>());
  const departed = useRef(new Set<string>());
  const queue = useRef(Promise.resolve());
  const failed = useRef<Mutation | null>(null);
  const terminal = useRef(false);
  const blocked = useRef(false);
  const inFlight = useRef(false);
  const sentValues = useRef(new Map<string, string>());
  const timer = useRef<number | null>(null);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState("");

  function updatePending() { setPending(dirty.current.size > 0 || blocked.current); }
  function schedule() {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    if (!mounted.current || blocked.current || inFlight.current || dirty.current.size === 0) return;
    const due = Math.min(...[...dirty.current.values()].map(item => item.since)) + 1000;
    timer.current = window.setTimeout(() => {
      timer.current = null;
      if (editor.current?.isComposing()) return;
      void enqueue(() => flush());
    }, Math.max(0, due - performance.now()));
  }
  function buffer(fields: FieldProjection[]) {
    const canonical = latest.current?.project?.document;
    if (!canonical) return;
    const saved = new Map(documentFields(canonical).map(field => [field.fieldId, field.text]));
    for (const field of fields) {
      if (saved.get(field.fieldId) === field.text) { dirty.current.delete(field.fieldId); continue; }
      if (!invalidated.current.has(field.fieldId)) {
        invalidated.current.add(field.fieldId);
        void enqueue(async () => {
          const id = latest.current?.projectId;
          if (id) await analysisRequest(id, "invalidate", [field.fieldId]);
        });
      }
      let sessionId = sessions.current.get(field.slotId) ?? latest.current?.editSessions[field.slotId]?.sessionId;
      if (!sessionId) sessionId = crypto.randomUUID();
      sessions.current.set(field.slotId, sessionId);
      const previous = dirty.current.get(field.fieldId), sent = sentValues.current.get(field.fieldId);
      const since = previous && !(previous.field.text === sent && field.text !== sent) ? previous.since : performance.now();
      dirty.current.set(field.fieldId, { field, sessionId, since });
    }
    updatePending(); schedule();
  }
  function enqueue(work: () => Promise<void>, kind: "write" | "read" = "write") {
    queue.current = queue.current.catch(() => {}).then(async () => {
      if (blocked.current) { setLocked(false); return; }
      inFlight.current = true;
      if (kind === "write") setSaving(true);
      try { await work(); }
      catch (error) { if (kind === "read") throw error;
        blocked.current = true; setError(error instanceof ApiFailure && error.code === "MUTATION_STALE"
        ? "Текст на сервере изменился. Ваш ввод сохранён в окне; повторите сохранение после проверки."
        : "Не удалось сохранить правки. Ввод остаётся в окне; повторите сохранение."); }
      finally { inFlight.current = false; if (kind === "write") setSaving(false); updatePending(); schedule(); }
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
    sentValues.current = sent;
    const result = await mutationRequest(request);
    const response = await projectRequest(`/v1/projects/${request.projectId}`);
    latest.current = response.workspace;
    acceptLatest.current(response);
    if (result.status === "stale" || result.status === "rejected" || result.rejectionReason !== null) {
      terminal.current = true;
      throw new ApiFailure("MUTATION_STALE");
    }
    if (result.persistence !== "durable") throw new ApiFailure("PROJECT_SAVE_FAILED");
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
    sentValues.current = new Map();
  }
  async function flush(slot?: string, completion: "none" | "slot" = "none") {
    const entries = [...dirty.current.values()].filter(item => slot === undefined || item.field.slotId === slot);
    for (const captured of entries) {
      const item = dirty.current.get(captured.field.fieldId);
      if (!item) continue;
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
        for (const value of editor.current?.read().filter(value => value.slotId === id) ?? []) invalidated.current.delete(value.fieldId);
      }
    }
  }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (timer.current !== null) clearTimeout(timer.current); };
  }, []);
  function departure(slot: string) {
    if (!sessions.current.has(slot)) return;
    departed.current.add(slot);
    void enqueue(async () => { await flush(slot, "slot"); departed.current.delete(slot); });
  }
  function restore(slot: string) {
    if (editor.current?.isComposing()) return;
    const captured = editor.current?.read().filter(field => field.slotId === slot) ?? [];
    for (const field of captured) invalidated.current.delete(field.fieldId);
    const capturedSession = sessions.current.get(slot) ?? latest.current?.editSessions[slot]?.sessionId ?? null;
    const wasDirty = captured.some(field => dirty.current.has(field.fieldId));
    void enqueue(async () => {
      if (wasDirty && capturedSession) {
        const document = latest.current?.project?.document;
        const saved = new Map(document ? documentFields(document).map(field => [field.fieldId, field.text]) : []);
        for (const field of captured) {
          if (saved.get(field.fieldId) !== field.text) await send({ ...base(), kind: "edit-field", payload: {
            fieldId: field.fieldId, text: field.text, periods: null, focus: null, sessionId: capturedSession, completion: "none",
          } }, new Map([[field.fieldId, field.text]]));
        }
      }
      const sent = new Map(captured.map(field => [field.fieldId, field.text]));
      await send({ ...base(), kind: "restore-previous-block", payload: { slotId: slot, sessionId: capturedSession } }, sent);
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
    const sessionId = sessions.current.get(field.slotId);
    invalidated.current.delete(fieldId);
    void enqueue(async () => {
      if (sessionId) await send({ ...base(), kind: "edit-field", payload: { fieldId, text: field.text,
        periods: null, focus: null, sessionId, completion: reason } }, new Map([[fieldId, field.text]]));
    });
  }
  function overlay(fields: FieldProjection[]) { return fields.map(field => ({ ...field, text: dirty.current.get(field.fieldId)?.field.text ?? field.text })); }
  async function flushBeforeAction(complete = false) {
    if (editor.current?.isComposing()) return false;
    await enqueue(() => flush(undefined, complete ? "slot" : "none"));
    return !blocked.current && dirty.current.size === 0;
  }
  async function acceptExternal(captured: ReadonlyMap<string, string>) {
    await enqueue(async () => {
      const id = latest.current?.projectId;
      if (!id) return;
      const response = await projectRequest(`/v1/projects/${id}`);
      const live = new Map(editor.current?.read().map(field => [field.fieldId, field.text]) ?? []);
      latest.current = response.workspace;
      acceptLatest.current(response);
      if (response.workspace.project) editor.current?.patch(documentFields(response.workspace.project.document)
        .filter(field => live.get(field.fieldId) === captured.get(field.fieldId) && live.get(field.fieldId) !== field.text)
        .map(field => ({ fieldId: field.fieldId, text: field.text, capturedText: live.get(field.fieldId) ?? "" })));
    }, "read");
  }
  return { buffer, departure, restore, structural, periods, retry, completion, compositionEnd: schedule, overlay,
    flushBeforeAction, acknowledged: () => latest.current, acceptExternal, pending, saving, locked, error };
}
