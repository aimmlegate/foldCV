import { ProjectEditorConnection } from "../rich/v7-connection";
import type { WriterViewV1 } from "../contracts/generated/background_writer_view_v1";
import type { WriterProofV1 } from "../contracts/generated/background_writer_proof_v1";
import type { DraftPayloadV1 } from "../contracts/generated/background_draft_payload_v1";
import { validateContract } from "../contracts/validate";
import { prepareWriterContracts } from "../contracts/background-validate";
import { imageSource, RichApiFailure } from "../rich/api";
import { WriterApi, type WriterTransport } from "./api";
import { BrowserDraftDatabase, DraftRepository, type LocalDraft } from "./drafts";
import { applicationTabActive } from "./tab";

type Resume = { schemaVersion: 1; proof: WriterProofV1; revision: number; sha256: string; cursor: number; sequence: number };
export type AttachedWriter = { api: WriterTransport; proof: WriterProofV1 | null; view: WriterViewV1;
  repository: DraftRepository; local: { record: LocalDraft; payload: DraftPayloadV1 } | null; error: string | null };
const database = new BrowserDraftDatabase();
export function draftRepository(project: string): DraftRepository {
  return new DraftRepository(database, async id => {
    const response = await fetch(imageSource(project, id), { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("DRAFT_ASSET_MISSING");
    return new Uint8Array(await response.arrayBuffer());
  });
}

function isResume(value: unknown): value is Resume {
  return typeof value === "object" && value !== null && "schemaVersion" in value && value.schemaVersion === 1
    && "proof" in value && validateContract("background_writer_proof_v1", value.proof)
    && "revision" in value && Number.isSafeInteger(value.revision) && Number(value.revision) >= 1
    && "sha256" in value && typeof value.sha256 === "string" && /^[0-9a-f]{64}$/u.test(value.sha256)
    && "cursor" in value && Number.isSafeInteger(value.cursor) && Number(value.cursor) >= 0
    && "sequence" in value && Number.isSafeInteger(value.sequence) && Number(value.sequence) >= 0;
}

type ResumeView = { response: { workspace: { projectRevision: number } }; workspaceSha256: string };
export function retainResume(project: string, proof: WriterProofV1, view: ResumeView, cursor: number, sequence: number): void {
  const key = `foldcv-writer:${project}`, wire = JSON.stringify({ schemaVersion: 1, proof,
    revision: view.response.workspace.projectRevision, sha256: view.workspaceSha256, cursor, sequence } satisfies Resume);
  sessionStorage.setItem(key, wire);
  if (applicationTabActive()) localStorage.setItem(key, wire);
}

export function attachExclusiveWriter(project: string): Promise<AttachedWriter | null> {
  return attachWriter(project, new WriterApi(project), draftRepository(project), applicationTabActive);
}

export async function attachWriter(project: string, api: WriterTransport = new WriterApi(project), repository = draftRepository(project),
  exclusiveTab: (() => boolean) | null = null): Promise<AttachedWriter | null> {
  const requireTab = () => { if (exclusiveTab && !exclusiveTab()) throw new Error("TAB_LOCK_REQUIRED"); };
  requireTab();
  let bootstrap: WriterViewV1;
  try { bootstrap = await api.bootstrap(); }
  catch (error) { if (error instanceof RichApiFailure && error.code === "JOB_DISABLED") return null; throw error; }
  requireTab();
  prepareWriterContracts();
  let previous: Resume | null = null, local: AttachedWriter["local"] = null;
  try {
    const key = `foldcv-writer:${project}`, candidates = [sessionStorage.getItem(key)];
    if (exclusiveTab) candidates.unshift(localStorage.getItem(key));
    for (const wire of candidates) {
      const stored: unknown = JSON.parse(wire ?? "null");
      if (isResume(stored) && stored.proof.lineage === bootstrap.writer.lineage) { previous = stored; break; }
    }
    local = await repository.read(project, bootstrap.writer.lineage, { epoch: bootstrap.writer.epoch, incarnation: bootstrap.writer.incarnation });
  } catch (error) {
    return { api, proof: null, view: bootstrap, repository, local: null, error: error instanceof Error ? error.message : "DRAFT_CORRUPT" };
  }
  if (!bootstrap.canonicalReady) return { api, proof: null, view: bootstrap, repository, local, error: "OUTCOME_UNKNOWN" };
  const credential = previous?.proof.credential ?? crypto.randomUUID() + crypto.randomUUID();
  const sessionId = previous?.proof.sessionId ?? crypto.randomUUID(), incarnation = crypto.randomUUID();
  try {
    requireTab();
    // A browser can close without delivering its writer's unload beacon.
    if (exclusiveTab && previous && bootstrap.writer.status !== "clean_detached"
      && previous.proof.epoch === bootstrap.writer.epoch && previous.proof.incarnation === bootstrap.writer.incarnation
      && previous.proof.sessionId === bootstrap.writer.sessionId) await api.suspend(previous.proof);
    requireTab();
    const clean = exclusiveTab !== null && previous?.sequence === 0 && !local;
    const view = await api.open({ schemaVersion: 1, sessionId, incarnation, credential,
      previousEpoch: previous?.proof.epoch ?? null, previousIncarnation: previous?.proof.incarnation ?? null,
      canonicalRevision: clean ? bootstrap.response.workspace.projectRevision : previous?.revision ?? bootstrap.response.workspace.projectRevision,
      canonicalSha256: clean ? bootstrap.workspaceSha256 : previous?.sha256 ?? bootstrap.workspaceSha256,
      actionCursor: local?.record.cursor ?? previous?.cursor ?? 0, draftSequence: local?.record.sequence ?? previous?.sequence ?? 0 });
    const proof: WriterProofV1 = { schemaVersion: 1, lineage: view.writer.lineage, epoch: view.writer.epoch,
      sessionId: view.writer.sessionId, incarnation: view.writer.incarnation, credential };
    retainResume(project, proof, view, local?.record.cursor ?? view.writer.acknowledgedCursor, local?.record.sequence ?? 0);
    requireTab();
    if (local && local.record.epoch !== proof.epoch) return { api, proof: null, view, repository, local, error: "DRAFT_OLD_EPOCH" };
    if (local && local.record.incarnation !== proof.incarnation) {
      if (local.record.incarnation !== previous?.proof.incarnation) return { api, proof: null, view, repository, local, error: "DRAFT_OLD_CONNECTION" };
      const replacement = { ...local.record, incarnation: proof.incarnation };
      try { await repository.replaceOwner(local.record, replacement); local = { ...local, record: replacement }; }
      catch { return { api, proof: null, view, repository, local, error: "DRAFT_STORAGE_FAILED" }; }
    }
    return { api, proof, view, repository, local, error: null };
  } catch (error) {
    if (error instanceof RichApiFailure && error.code === "WRITER_UNKNOWN") return { api, proof: null, view: bootstrap, repository, local, error: "WRITER_READ_ONLY" };
    throw error;
  }
}

export type AttachedTemplateWriter = ProjectEditorConnection;

export async function attachExclusiveTemplateWriter(project: string): Promise<ProjectEditorConnection> {
  if (!applicationTabActive()) throw new Error("TAB_LOCK_REQUIRED");
  const connection = await ProjectEditorConnection.open(project);
  if (!applicationTabActive()) throw new Error("TAB_LOCK_REQUIRED");
  return connection;
}
