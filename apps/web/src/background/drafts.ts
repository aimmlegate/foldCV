import type { DraftPayloadV1 } from "../contracts/generated/background_draft_payload_v1";
import type { DraftPayloadV2 } from "../contracts/generated/background_writer_draft_payload_v2";
import { validateBackgroundShape } from "../contracts/background-validate";
import { isTemplateDraftPayload } from "../contracts/template-drafts";
import { sha256 } from "./wire";

export type LocalDraft = { schemaVersion: 1; project: string; lineage: string; epoch: number; incarnation: string; id: string; sequence: number;
  cursor: number; baseRevision: number; baseSha256: string; payloadWire: string; payloadSha256: string;
  assets: { id: string; sha256: string }[] };
export type DraftDatabase = { transact: <T>(work: (rows: LocalDraft[]) => { rows: LocalDraft[]; result: T }) => Promise<T>;
  discardProject: (project: string) => Promise<void> };
export type DraftAssets = (id: string) => Promise<Uint8Array<ArrayBuffer>>;
export const draftLimits = { project: 2 * 1024 * 1024, global: 8 * 1024 * 1024 } as const;

function valid(row: unknown): row is LocalDraft {
  if (typeof row !== "object" || row === null || !("schemaVersion" in row) || row.schemaVersion !== 1) return false;
  const strings = ["project", "lineage", "incarnation", "id", "baseSha256", "payloadWire", "payloadSha256"];
  const numbers = ["epoch", "sequence", "cursor", "baseRevision"];
  return strings.every(key => key in row && typeof Reflect.get(row, key) === "string")
    && numbers.every(key => key in row && Number.isSafeInteger(Reflect.get(row, key)) && Number(Reflect.get(row, key)) >= (key === "cursor" ? 0 : 1))
    && "assets" in row && Array.isArray(row.assets) && row.assets.every((asset: unknown) => typeof asset === "object" && asset !== null
      && "id" in asset && typeof asset.id === "string" && "sha256" in asset && typeof asset.sha256 === "string");
}

export class BrowserDraftDatabase implements DraftDatabase {
  private database: Promise<IDBDatabase> | null = null;
  async discardProject(project: string): Promise<void> {
    const db = await this.open();
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("drafts", "readwrite"), request = transaction.objectStore("drafts").openCursor();
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) return;
        const key = cursor.primaryKey;
        if (key === project || Array.isArray(key) && key[0] === project) cursor.delete();
        cursor.continue();
      };
      transaction.oncomplete = () => resolve(); transaction.onabort = () => reject(transaction.error ?? new Error("DRAFT_STORAGE_FAILED"));
    });
  }
  private open(): Promise<IDBDatabase> {
    return this.database ??= new Promise((resolve, reject) => {
      const request = indexedDB.open("foldcv-background-drafts", 1);
      request.onupgradeneeded = () => { request.result.createObjectStore("drafts", { keyPath: ["project", "epoch", "incarnation", "id"] }); };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("DRAFT_STORAGE_FAILED"));
      request.onblocked = () => reject(new Error("DRAFT_STORAGE_BLOCKED"));
    });
  }
  async transact<T>(work: (rows: LocalDraft[]) => { rows: LocalDraft[]; result: T }): Promise<T> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("drafts", "readwrite"), store = transaction.objectStore("drafts");
      let outcome: { result: T } | null = null, failure: unknown = null;
      transaction.oncomplete = () => outcome ? resolve(outcome.result) : reject(new Error("DRAFT_STORAGE_FAILED"));
      transaction.onabort = () => reject(failure ?? transaction.error ?? new Error("DRAFT_STORAGE_FAILED"));
      transaction.onerror = () => { failure ??= transaction.error; };
      const request = store.getAll();
      request.onsuccess = () => {
        try {
          const rows: unknown = request.result;
          if (!Array.isArray(rows) || !rows.every(valid)) throw new Error("DRAFT_CORRUPT");
          const next = work(rows); outcome = next;
          store.clear(); next.rows.forEach(row => store.put(row));
        } catch (error) { failure = error; transaction.abort(); }
      };
    });
  }
}

export class DraftRepository {
  constructor(private readonly database: DraftDatabase, private readonly assets: DraftAssets) {}
  async write(row: LocalDraft): Promise<LocalDraft> {
    if (new TextEncoder().encode(JSON.stringify(row)).length > draftLimits.project) throw new Error("DRAFT_STORAGE_FULL");
    await this.verify(row, row.project, row.lineage);
    return this.database.transact(rows => {
      const sameKey = (item: LocalDraft) => item.project === row.project && item.epoch === row.epoch && item.incarnation === row.incarnation && item.id === row.id;
      const old = rows.find(sameKey);
      if (old && old.lineage !== row.lineage) throw new Error("DRAFT_RESOLUTION_REQUIRED");
      if (old && old.sequence > row.sequence) return { rows, result: old };
      if (old && old.sequence === row.sequence) {
        if (JSON.stringify(old) !== JSON.stringify(row)) throw new Error("DRAFT_IDEMPOTENCY_CONFLICT");
        return { rows, result: old };
      }
      if (old && old.cursor > row.cursor) throw new Error("DRAFT_CURSOR_REGRESSED");
      const next = [...rows.filter(item => !sameKey(item)), structuredClone(row)];
      const size = (item: LocalDraft) => new TextEncoder().encode(JSON.stringify(item)).length;
      if (next.filter(item => item.project === row.project).reduce((sum, item) => sum + size(item), 0) > draftLimits.project
        || next.reduce((sum, item) => sum + size(item), 0) > draftLimits.global) throw new Error("DRAFT_STORAGE_FULL");
      return { rows: next, result: row };
    });
  }
  async read(project: string, lineage: string, owner?: { epoch: number; incarnation: string }): Promise<{ record: LocalDraft; payload: DraftPayloadV1 } | null> {
    const row = await this.database.transact(rows => {
      const candidates = rows.filter(item => item.project === project).sort((a, b) => b.epoch - a.epoch || b.sequence - a.sequence);
      return { rows, result: candidates.find(item => item.epoch === owner?.epoch && item.incarnation === owner.incarnation) ?? candidates[0] ?? null };
    });
    if (!row) return null;
    const payload = await this.verify(row, project, lineage);
    if (payload.schemaVersion !== 1) throw new Error("DRAFT_CORRUPT");
    return { record: row, payload };
  }
  /** The V7 family of the same store: V2 payloads with an optional queue record. */
  async readTemplate(project: string, lineage: string, owner?: { epoch: number; incarnation: string }): Promise<{ record: LocalDraft; payload: DraftPayloadV2 } | null> {
    const row = await this.database.transact(rows => {
      const candidates = rows.filter(item => item.project === project).sort((a, b) => b.epoch - a.epoch || b.sequence - a.sequence);
      return { rows, result: candidates.find(item => item.epoch === owner?.epoch && item.incarnation === owner.incarnation) ?? candidates[0] ?? null };
    });
    if (!row) return null;
    const payload = await this.verify(row, project, lineage);
    if (payload.schemaVersion !== 2) throw new Error("DRAFT_CORRUPT");
    return { record: row, payload };
  }
  async remove(row: LocalDraft): Promise<void> {
    await this.database.transact(rows => {
      const sameKey = (item: LocalDraft) => item.project === row.project && item.epoch === row.epoch && item.incarnation === row.incarnation && item.id === row.id;
      const old = rows.find(sameKey);
      if (old && (old.lineage !== row.lineage || old.epoch !== row.epoch || old.sequence !== row.sequence || old.payloadSha256 !== row.payloadSha256)) throw new Error("DRAFT_CHANGED");
      return { rows: rows.filter(item => !sameKey(item)), result: undefined };
    });
  }
  discardProject(project: string): Promise<void> { return this.database.discardProject(project); }
  async replaceOwner(previous: LocalDraft, next: LocalDraft): Promise<void> {
    if (previous.project !== next.project) throw new Error("DRAFT_CHANGED");
    await this.verify(next, next.project, next.lineage);
    await this.database.transact(rows => {
      const sameKey = (item: LocalDraft) => item.project === previous.project && item.epoch === previous.epoch && item.incarnation === previous.incarnation && item.id === previous.id;
      const old = rows.find(sameKey);
      if (!old || JSON.stringify(old) !== JSON.stringify(previous)) throw new Error("DRAFT_CHANGED");
      const remaining = rows.filter(item => !sameKey(item));
      if (remaining.some(item => item.project === next.project && item.epoch === next.epoch && item.incarnation === next.incarnation && item.id === next.id)) throw new Error("DRAFT_CHANGED");
      const result = [...remaining, next];
      const size = (row: LocalDraft) => new TextEncoder().encode(JSON.stringify(row)).length;
      if (result.filter(item => item.project === next.project).reduce((sum, row) => sum + size(row), 0) > draftLimits.project
        || result.reduce((sum, row) => sum + size(row), 0) > draftLimits.global) throw new Error("DRAFT_STORAGE_FULL");
      return { rows: result, result: undefined };
    });
  }
  private async verify(row: LocalDraft, project: string, lineage: string): Promise<DraftPayloadV1 | DraftPayloadV2> {
    if (!valid(row) || row.project !== project || row.lineage !== lineage || await sha256(row.payloadWire) !== row.payloadSha256) throw new Error("DRAFT_CORRUPT");
    const payload: unknown = JSON.parse(row.payloadWire);
    if (!isPayload(payload) && !isTemplateDraftPayload(payload)) throw new Error("DRAFT_CORRUPT");
    if (new Set(row.assets.map(item => item.id)).size !== row.assets.length || payload.assetPins.some(id => !row.assets.some(item => item.id === id))) throw new Error("DRAFT_ASSET_MISSING");
    await Promise.all(row.assets.map(async asset => { if (await sha256(await this.assets(asset.id)) !== asset.sha256) throw new Error("DRAFT_ASSET_MISSING"); }));
    return payload;
  }
}

function isPayload(value: unknown): value is DraftPayloadV1 { return validateBackgroundShape("background_draft_payload_v1", value); }
