import { validateContract } from "../contracts/validate";
import { validateBackgroundWire } from "../contracts/background-validate";
import { request, requestWire, rootRequest, RichApiFailure } from "../rich/api";
import type { JsonWireNode } from "../contracts/lossless-json";
import type { WriterPrepareEditV2 } from "../contracts/generated/background_writer_prepare_edit_v2";
import { prepareTemplateTransport, saveTemplateTransport, type BoundTemplatePreparation } from "../contracts/template-transport";
import type { PreparedSaveOpening } from "../contracts/template-save";
import type { JobSummaryV1 } from "../contracts/generated/background_summary_v1";
import type { JobIndexV1 } from "../contracts/generated/background_index_v1";
import type { WriterViewV1 } from "../contracts/generated/background_writer_view_v1";
import type { WriterViewV2 } from "../contracts/generated/background_writer_view_v2";
import type { WriterMutationV2 } from "../contracts/generated/background_writer_mutation_v2";
import type { WriterLocalHistoryCommandV2 } from "../contracts/generated/background_writer_local_history_command_v2";
import { templateWriterReply } from "../contracts/template-validate";
import type { WriterOpenV1 } from "../contracts/generated/background_writer_open_v1";
import type { WriterProofV1 } from "../contracts/generated/background_writer_proof_v1";
import type { WriterAdvanceV1 } from "../contracts/generated/background_writer_advance_v1";
import type { WriterBarrierAckV1 } from "../contracts/generated/background_writer_barrier_ack_v1";
import type { WriterBarrierCommandV1 } from "../contracts/generated/background_writer_barrier_command_v1";
import type { WriterCheckpointV1 } from "../contracts/generated/background_writer_checkpoint_v1";
import type { WriterDraftCommandV1 } from "../contracts/generated/background_writer_draft_command_v1";
import type { WriterDraftResolveV1 } from "../contracts/generated/background_writer_draft_resolve_v1";
import type { JobFixedRequestV1 } from "../contracts/generated/background_fixed_request_v1";
import type { JobFixedReplyV1 } from "../contracts/generated/background_fixed_reply_v1";
import type { WriterDraftReadV1 } from "../contracts/generated/background_writer_draft_read_v1";
import type { WriterAbandonV1 } from "../contracts/generated/background_writer_abandon_v1";
import type { WriterMutationV1 } from "../contracts/generated/background_writer_mutation_v1";
import type { WriterPublishV1 } from "../contracts/generated/background_writer_publish_v1";
import type { WriterPublicationV1 } from "../contracts/generated/background_writer_publication_v1";
import type { WriterHistoryRequestV1 } from "../contracts/generated/background_writer_history_request_v1";
import type { WriterHistoryOfferV1 } from "../contracts/generated/background_writer_history_offer_v1";
import type { WriterHistoryCommandV1 } from "../contracts/generated/background_writer_history_command_v1";
import type { WriterHistoryResultV1 } from "../contracts/generated/background_writer_history_result_v1";
import type { PublicationBarrierV1 } from "../contracts/generated/background_barrier_v1";
import type { DraftCheckpointV1 } from "../contracts/generated/background_draft_v1";
import type { UndoOwnershipV1 } from "../contracts/generated/background_undo_v1";
import type { JobProjectV1 } from "../contracts/generated/background_project_v1";
import type { JobSnapshotV1 } from "../contracts/generated/background_snapshot_v1";
import type { JobReplayV1 } from "../contracts/generated/background_replay_v1";
import type { JobAgentRequestV1 } from "../contracts/generated/background_agent_request_v1";
import type { ProposalBindingV1 } from "../contracts/generated/background_proposal_v1";
import type { AgentConversation } from "../contracts/generated/agent_conversation";
import type { AgentMessage } from "../contracts/generated/agent_message";
import type { JobLegacyRunV2 } from "../contracts/generated/background_legacy_run_v2";

type Replies = { background_writer_view_v1: WriterViewV1; background_barrier_v1: PublicationBarrierV1;
  background_draft_v1: DraftCheckpointV1; background_writer_draft_read_v1: WriterDraftReadV1;
  background_writer_publication_v1: WriterPublicationV1; background_writer_history_offer_v1: WriterHistoryOfferV1;
  background_undo_v1: UndoOwnershipV1; background_writer_history_result_v1: WriterHistoryResultV1;
  background_project_v1: JobProjectV1; background_snapshot_v1: JobSnapshotV1; background_replay_v1: JobReplayV1;
  background_proposal_v1: ProposalBindingV1; background_legacy_run_v2: JobLegacyRunV2;
  background_fixed_reply_v1: JobFixedReplyV1; background_summary_v1: JobSummaryV1; background_index_v1: JobIndexV1 };
export type BackgroundConversation = Omit<AgentConversation, "messages"> & { messages: AgentMessage[] };
export type BackgroundRequest = (path: string, method?: string, body?: unknown) => Promise<unknown>;

export class GlobalJobsApi {
  constructor(private readonly transport: () => Promise<unknown> = () => rootRequest("/v1/background/jobs")) {}
  async index(): Promise<JobIndexV1> { return backgroundReply("background_index_v1", await this.transport()); }
}

export async function backgroundReply<K extends keyof Replies>(kind: K, value: unknown): Promise<Replies[K]> {
  if (!validateContract(kind, value) || !await validateBackgroundWire(kind, value)) throw new RichApiFailure("INVALID_RESULT");
  return value as Replies[K];
}

export class WriterApi {
  readonly prefix: string;
  constructor(readonly project: string, private readonly transport: BackgroundRequest = request,
    private readonly wireTransport: (path: string, body: JsonWireNode) => Promise<unknown> = requestWire) { this.prefix = `/${encodeURIComponent(project)}/writer`; }
  private async call<K extends keyof Replies>(kind: K, path: string, body?: unknown): Promise<Replies[K]> {
    return backgroundReply(kind, await this.transport(this.prefix + path, body === undefined ? "GET" : "POST", body));
  }
  private async templateCall(path: string, body?: unknown): Promise<WriterViewV2> {
    const response = await templateWriterReply(await this.transport(this.prefix + path, body === undefined ? "GET" : "POST", body));
    if (!response || response.writer.projectId !== this.project) throw new RichApiFailure("INVALID_RESULT");
    return response;
  }
  templateBootstrap(): Promise<WriterViewV2> { return this.templateCall(""); }
  templateOpen(body: WriterOpenV1): Promise<WriterViewV2> { return this.templateCall("/open", body); }
  templateRead(body: WriterProofV1): Promise<WriterViewV2> { return this.templateCall("/read", body); }
  templateSave(body: WriterMutationV2): Promise<WriterViewV2> { return this.templateCall("/save", body); }
  templateHistory(body: WriterLocalHistoryCommandV2): Promise<WriterViewV2> { return this.templateCall("/history/local", body); }
  templatePrepareDelta(base: JsonWireNode, body: WriterPrepareEditV2) {
    return prepareTemplateTransport(this.project, base, body, request => this.transport(this.prefix + "/prepare-delta", "POST", request));
  }
  templateSavePrepared(body: JsonWireNode, preparation: BoundTemplatePreparation, opening: PreparedSaveOpening) {
    return saveTemplateTransport(this.project, body, preparation, opening, request => this.wireTransport(this.prefix + "/save", request));
  }
  bootstrap(): Promise<WriterViewV1> { return this.call("background_writer_view_v1", ""); }
  open(body: WriterOpenV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/open", body); }
  heartbeat(body: WriterProofV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/heartbeat", body); }
  read(body: WriterProofV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/read", body); }
  suspend(body: WriterProofV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/suspend", body); }
  flush(body: WriterAdvanceV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/flush", body); }
  reconcile(body: WriterAdvanceV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/reconcile", body); }
  detach(body: WriterAdvanceV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/detach", body); }
  save(body: WriterMutationV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/save", body); }
  barrier(body: WriterBarrierAckV1): Promise<PublicationBarrierV1> { return this.call("background_barrier_v1", "/barrier", body); }
  revoke(body: WriterBarrierCommandV1): Promise<PublicationBarrierV1> { return this.call("background_barrier_v1", "/revoke", body); }
  checkpoint(body: WriterCheckpointV1): Promise<DraftCheckpointV1> { return this.call("background_draft_v1", "/checkpoint", body); }
  draft(proof: WriterProofV1, id: string): Promise<WriterDraftReadV1> { return this.call("background_writer_draft_read_v1", "/draft/read", { schemaVersion: 1, proof, id }); }
  discard(body: WriterDraftCommandV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/draft/discard", body); }
  recover(body: WriterDraftCommandV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/draft/recover", body); }
  useDraft(body: WriterDraftResolveV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/draft/use", body); }
  abandon(body: WriterAbandonV1): Promise<WriterViewV1> { return this.call("background_writer_view_v1", "/abandon", body); }
  publish(body: WriterPublishV1): Promise<WriterPublicationV1> { return this.call("background_writer_publication_v1", "/publish", body); }
  offer(body: WriterHistoryRequestV1): Promise<WriterHistoryOfferV1> { return this.call("background_writer_history_offer_v1", "/history/offer", body); }
  begin(body: WriterHistoryRequestV1): Promise<UndoOwnershipV1> { return this.call("background_undo_v1", "/history/begin", body); }
  acknowledge(body: WriterHistoryRequestV1): Promise<UndoOwnershipV1> { return this.call("background_undo_v1", "/history/ack", body); }
  history(body: WriterHistoryCommandV1): Promise<WriterHistoryResultV1> { return this.call("background_writer_history_result_v1", "/history/command", body); }
}

export class JobsApi {
  readonly prefix: string;
  constructor(readonly project: string, private readonly transport: BackgroundRequest = request) { this.prefix = `/${encodeURIComponent(project)}/jobs`; }
  private async call<K extends keyof Replies>(kind: K, path: string, body?: unknown): Promise<Replies[K]> {
    return backgroundReply(kind, await this.transport(this.prefix + path, body === undefined ? "GET" : "POST", body));
  }
  projectJobs(): Promise<JobProjectV1> { return this.call("background_project_v1", ""); }
  submit(body: JobAgentRequestV1): Promise<JobSnapshotV1> { return this.call("background_snapshot_v1", "/agent", body); }
  fixed(body: JobFixedRequestV1): Promise<JobFixedReplyV1> { return this.call("background_fixed_reply_v1", "/fixed", body); }
  read(id: string): Promise<JobSnapshotV1> { return this.call("background_snapshot_v1", `/${encodeURIComponent(id)}/read`, {}); }
  cancel(id: string): Promise<JobSnapshotV1> { return this.call("background_snapshot_v1", `/${encodeURIComponent(id)}/cancel`, {}); }
  discard(id: string): Promise<JobSnapshotV1> { return this.call("background_snapshot_v1", `/${encodeURIComponent(id)}/discard`, {}); }
  proposal(id: string): Promise<ProposalBindingV1> { return this.call("background_proposal_v1", `/${encodeURIComponent(id)}/proposal/read`, {}); }
  legacy(id: string): Promise<JobLegacyRunV2> { return this.call("background_legacy_run_v2", `/${encodeURIComponent(id)}/legacy-v2`, {}); }
  async conversation(id: string): Promise<BackgroundConversation> {
    const value = await this.transport(this.prefix + `/${encodeURIComponent(id)}/conversation/read`, "POST", {});
    if (!validateContract("agent_conversation", value) || typeof value !== "object" || value === null || !("messages" in value)
      || !Array.isArray(value.messages) || !value.messages.every((message: unknown) => validateContract("agent_message", message))) throw new RichApiFailure("INVALID_RESULT");
    return value as BackgroundConversation;
  }
  replay(id: string, generation: number, after: number): Promise<JobReplayV1> {
    return this.call("background_replay_v1", `/${encodeURIComponent(id)}/replay`, { schemaVersion: 1, generation, after });
  }
}

export type WriterTransport = Pick<WriterApi, "project" | "bootstrap" | "open" | "heartbeat" | "read" | "suspend" | "flush" | "reconcile" | "detach"
  | "save" | "barrier" | "revoke" | "checkpoint" | "draft" | "discard" | "recover" | "useDraft" | "abandon" | "publish" | "offer" | "begin" | "acknowledge" | "history">;
