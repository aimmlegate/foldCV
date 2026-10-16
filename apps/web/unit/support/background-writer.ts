import assert from "node:assert/strict";
import fixture from "../../../../contracts/examples/background/background_writer_bridge.json" with { type: "json" };
import { backgroundReply, type WriterTransport } from "../../src/background/api";
import { BackgroundWriter, type WriterMode, type WriterObserver } from "../../src/background/writer";
import { DraftRepository, type DraftDatabase, type LocalDraft } from "../../src/background/drafts";
import type { AttachedWriter } from "../../src/background/connection";
import { sha256 } from "../../src/background/wire";
import { validateContract } from "../../src/contracts/validate";
import type { WriterProofV1 } from "../../src/contracts/generated/background_writer_proof_v1";
import type { WriterViewV1 } from "../../src/contracts/generated/background_writer_view_v1";
import type { RichProjectResponse } from "../../src/contracts/generated/rich_project_response";
import type { RichDocumentV1 } from "../../src/contracts/generated/rich_document_v1";
import type { RichMutation } from "../../src/contracts/generated/rich_mutation";
import { documentCells, type StoredBlock } from "../../src/rich/document-cells";
import { factCells, factsFromCells } from "../../src/rich/fact-cells";
import { SessionHistory, type CellValue } from "../../src/rich/history";
import { RichSaveQueue, type RichBlock } from "../../src/rich/save-queue";

const raw: Record<string, unknown> = fixture;
assert.ok(validateContract("background_writer_proof_v1", raw.proof));
export const proof = raw.proof as WriterProofV1;
export const before = await backgroundReply("background_writer_view_v1", raw.before);
export const published = await backgroundReply("background_writer_view_v1", raw.published);
export const owned = await backgroundReply("background_writer_view_v1", raw.owned);
export const job = await backgroundReply("background_snapshot_v1", raw.job);
export const saved = await backgroundReply("background_snapshot_v1", raw.saved);
export const proposal = await backgroundReply("background_proposal_v1", raw.proposal);
export const offer = await backgroundReply("background_writer_history_offer_v1", raw.offer);
export const newerOffer = await backgroundReply("background_writer_history_offer_v1", raw.newerOffer);
export const owner = await backgroundReply("background_undo_v1", raw.owner);
export const barrier = await backgroundReply("background_barrier_v1", raw.barrier);
export const undone = await backgroundReply("background_writer_history_result_v1", raw.undone);

class StorageFixture implements Storage {
  private readonly values = new Map<string, string>();
  get length(): number { return this.values.size; }
  clear(): void { this.values.clear(); }
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  key(index: number): string | null { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string): void { this.values.delete(key); }
  setItem(key: string, value: string): void { this.values.set(key, value); }
}
Object.defineProperty(globalThis, "sessionStorage", { value: new StorageFixture(), configurable: true });
Object.defineProperty(globalThis, "localStorage", { value: new StorageFixture(), configurable: true });

export function deferred<T>() {
  let resolve: (value: T) => void = () => {}, reject: (error: unknown) => void = () => {};
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
export class MemoryDraftDatabase implements DraftDatabase {
  rows: LocalDraft[] = [];
  failure: Error | null = null;
  discardProject(project: string): Promise<void> {
    if (this.failure) return Promise.reject(this.failure);
    this.rows = this.rows.filter(row => row.project !== project); return Promise.resolve();
  }
  transact<T>(work: (rows: LocalDraft[]) => { rows: LocalDraft[]; result: T }): Promise<T> {
    if (this.failure) return Promise.reject(this.failure);
    try { const next = work(structuredClone(this.rows)); this.rows = structuredClone(next.rows); return Promise.resolve(next.result); }
    catch (error) { return Promise.reject(error); }
  }
}

export function harness({ headless = false, initialView, proof: writerProof = proof, transport, attached,
  writerClass = BackgroundWriter, onSaved = () => {}, observe = () => Promise.resolve() }: {
  headless?: boolean; initialView?: WriterViewV1; proof?: WriterProofV1; transport?: WriterTransport; attached?: AttachedWriter;
  writerClass?: typeof BackgroundWriter; onSaved?: () => void; observe?: WriterObserver } = {}) {
  const proof = attached?.proof ?? writerProof;
  const initial = structuredClone(attached?.view ?? initialView ?? (headless ? owned : before)), maybeProject = initial.response.workspace.project;
  assert.ok(maybeProject); const project = maybeProject;
  const cache = new Map<string, StoredBlock>();
  const cells = (response: RichProjectResponse) => {
    const value = response.workspace.project; assert.ok(value);
    return new Map([...documentCells(value.document, cache), ...factCells(value.facts)]);
  };
  const mounted = cells(attached?.local ? { ...initial.response, workspace: { ...initial.response.workspace,
    project: { ...project, document: attached.local.payload.document, facts: attached.local.payload.facts } } } : initial.response);
  const rebuild = (id: string): RichBlock => {
    const value = mounted.get(`block:${id}`), stored = value ? cache.get(value) : null; assert.ok(stored);
    return { ...stored.block, children: stored.children.map(rebuild) };
  };
  function snapshot() {
    const regions = project.document.regions.map(region => {
      const ids: unknown = JSON.parse(mounted.get(`region:${region.id}`) ?? "[]");
      assert.ok(Array.isArray(ids) && ids.every((id: unknown) => typeof id === "string"));
      return { ...region, blocks: (ids as string[]).map(rebuild) };
    });
    const [header, sidebar, main] = regions; assert.ok(header && sidebar && main);
    const document: RichDocumentV1 = { schemaVersion: 1, revision: project.document.revision, regions: [header, sidebar, main] };
    return { document, facts: factsFromCells(mounted, project.facts), assets: [] };
  }
  let writer: BackgroundWriter | null = null, remoteHistory = false;
  const modes: WriterMode[] = [], hooks: string[] = [], errors: string[] = [];
  const counts = { commits: 0, saves: 0, notices: 0, ownership: 0, history: 0, cancels: 0 };
  let state = initial, canonicalSaved = headless, currentCursor = 0, touchGeneration = initial.writer.touchGeneration;
  let publishReply = () => Promise.resolve({ schemaVersion: 1 as const, job: structuredClone(saved), view: view(published) });
  let offerReply = () => Promise.resolve(structuredClone(offer));
  const savedView = initialView ?? owned;
  let readReply = () => Promise.resolve(view(canonicalSaved ? savedView : initial));
  function view(source: WriterViewV1): WriterViewV1 {
    return { ...structuredClone(source), writer: { ...source.writer, acknowledgedCursor: currentCursor,
      touchGeneration, barrierGeneration: state.writer.barrierGeneration } };
  }
  const mockApi: WriterTransport = {
    project: before.response.workspace.projectId,
    bootstrap: () => readReply(), open: () => Promise.reject(new Error("Unexpected open")),
    heartbeat: () => readReply(), read: () => readReply(), suspend: () => Promise.resolve(view(state)),
    flush: request => { currentCursor = Math.max(currentCursor, request.actionCursor); touchGeneration++;
      state = view(canonicalSaved ? savedView : initial); return Promise.resolve(structuredClone(state)); },
    reconcile: () => Promise.resolve(view(owned)),
    detach: () => Promise.resolve({ ...view(state), writer: { ...view(state).writer, status: "clean_detached" } }),
    save: () => { counts.saves++; return Promise.reject(new Error("Unexpected manual save")); },
    barrier: request => { state.writer.barrierGeneration = request.generation; return Promise.resolve({ ...barrier,
      generation: request.generation, token: request.token, actionCursor: request.actionCursor, touchGeneration: request.touchGeneration }); },
    revoke: () => Promise.resolve({ ...barrier, state: canonicalSaved ? "resolved" : "revoked" }),
    checkpoint: request => Promise.resolve({ schemaVersion: 1, id: request.id, projectId: api.project, lineage: proof.lineage,
      writerEpoch: proof.epoch, incarnation: proof.incarnation, sequence: request.sequence, actionCursor: request.actionCursor,
      baseRevision: request.baseRevision, baseSha256: request.baseSha256, payloadRef: "synthetic-draft", payloadSha256: "a".repeat(64),
      payloadBytes: 1, touches: [], checkpointedAt: barrier.expiresAt }),
    draft: () => Promise.reject(new Error("Unexpected draft read")), discard: () => Promise.resolve(view(owned)),
    recover: () => Promise.resolve(view(owned)), useDraft: () => Promise.reject(new Error("Unexpected draft resolution")),
    abandon: () => Promise.reject(new Error("Unexpected abandonment")),
    publish: () => { if (!canonicalSaved) counts.commits++; canonicalSaved = true; return publishReply(); },
    offer: () => offerReply(), begin: () => Promise.resolve({ ...owner, owner: "transferring" }),
    acknowledge: () => { counts.ownership++; return Promise.resolve(owner); },
    history: request => { counts.history++; currentCursor = request.actionCursor;
      return Promise.resolve({ ...structuredClone(undone), receipt: { ...undone.receipt, commandId: request.commandId }, view: view(undone.view) }); },
  };
  const api = attached?.api ?? transport ?? mockApi;
  const history = new SessionHistory(proof.sessionId, mounted, (changes, context) => {
    changes.forEach(change => mounted.set(change.key, change.after));
    if (context.mode !== "prepared" && !remoteHistory && writer) {
      writer.input(context.kind === "undo" || context.kind === "redo" ? context.kind : "typing");
      if (writer.mode === "normal") { const value = snapshot(); queue.update(value.document, "local-input", "typing", value.facts); }
    }
  }, context => !writer || writer.writable || context.mode === "prepared" || remoteHistory);
  const queue = new RichSaveQueue(initial.response, proof.sessionId, request => {
    assert.ok(writer); return writer.save(request);
  }, () => {});
  let alarm: (() => void) | null = null, locked = false;
  const alarmDeliveries: (() => void)[] = [];
  let composition: Promise<void> = Promise.resolve();
  const database = new MemoryDraftDatabase(), repository = attached?.repository ?? new DraftRepository(database, () => Promise.reject(new Error("Unexpected image")));
  const connection: AttachedWriter = attached ?? { api, proof, view: initial, repository, local: null, error: null };
  writer = new writerClass(connection, { queue, history, snapshot, cells, flushLocal: () => queue.flush(),
    compositionEnd: () => composition, lock: value => { locked = value; }, changed: (mode, error) => { modes.push(mode); if (error) errors.push(error); },
    saved: () => { counts.notices++; onSaved(); }, applyHistory: direction => {
      remoteHistory = true; try { return direction === "undo" ? history.undo() : history.redo(); } finally { remoteHistory = false; }
    } }, { alarm: callback => { alarm = callback; alarmDeliveries.push(callback); return () => { alarm = null; }; } }, async name => { hooks.push(name); await observe(name); });
  function type(text: string) {
    const old = history.read("block:quote"); assert.ok(old);
    const stored = cache.get(old); assert.ok(stored && Array.isArray(stored.block.content));
    const changed = structuredClone(stored); assert.ok(Array.isArray(changed.block.content));
    const span = changed.block.content[0]; assert.ok(span && "text" in span); span.text = text;
    const value = JSON.stringify(changed); cache.set(value, changed);
    return history.commit("typing", [{ key: "block:quote", before: old, after: value }]);
  }
  return { writer, api, connection, queue, history, mounted, cells, snapshot, modes, hooks, errors, counts, database, cache,
    type, locked: () => locked, expire: () => { assert.ok(alarm); alarm(); },
    lateAlarm: () => { const callback = alarmDeliveries[0]; assert.ok(callback); callback(); },
    composition: (value: Promise<void>) => { composition = value; },
    publishReply: (value: typeof publishReply) => { publishReply = value; },
    offerReply: (value: typeof offerReply) => { offerReply = value; }, readReply: (value: typeof readReply) => { readReply = value; },
    async settle() { await Promise.resolve(); await Promise.resolve(); },
    async localDraft() { return repository.read(api.project, proof.lineage); },
    async viewProof(value: WriterViewV1) { value.workspaceWire = JSON.stringify(value.response.workspace); value.workspaceSha256 = await sha256(value.workspaceWire); return value; },
    close() { writer.close(); history.close(); queue.close(); assert.equal(alarm, null); },
  };
}
