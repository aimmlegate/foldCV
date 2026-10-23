import type { AgentCapabilities } from "../contracts/generated/agent_capabilities";
import type { AssistantTaskCatalogV1 } from "../contracts/generated/assistant_task_catalog_v1";
import type { AgentSettings } from "../contracts/generated/agent_settings";
import type { AgentConversationPage } from "../contracts/generated/agent_conversation_page";
import type { AgentMessage } from "../contracts/generated/agent_message";
import type { AgentWebSource } from "../contracts/generated/agent_web_source";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import type { AgentRun } from "../contracts/generated/agent_run";
import type { AgentRunRequest } from "../contracts/generated/agent_run_request";
import type { AgentHistoryOffer } from "../contracts/generated/agent_history_offer";
import type { AgentEditReceipt } from "../contracts/generated/agent_edit_receipt";
import type { AgentEvent } from "../contracts/generated/agent_event";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { AgentApiFailure, type AgentBrowserApi, type AgentFlags, type AgentOwner } from "./api";
import type { PreparedApi, PreparedActionApi } from "./editor-bridge";
import type { AssistantCapabilityReviewV1 } from "../contracts/generated/assistant_capability_review_v1";
import type { AssistantHistoryOfferV1 } from "../contracts/generated/assistant_history_offer_v1";
import type { JobAgentRequestV1 } from "../contracts/generated/background_agent_request_v1";
import type { BackgroundConversation } from "../background/api";
import type { ProjectJobs } from "../background/jobs";
import { RichApiFailure } from "../rich/api";
import type { AssistantProposalV1 } from "../contracts/generated/assistant_proposal_v1";
import type { AssistantReviewV1 } from "../contracts/generated/assistant_review_v1";
import type { AssistantAcceptanceV1 } from "../contracts/generated/assistant_acceptance_v1";
import { proposalKey, proposalRequest } from "./proposal";

export const terminal = (run: AgentRun | null): boolean => run !== null && ["completed", "failed", "cancelled", "interrupted"].includes(run.state);
export type AssistantView = {
  taskCatalog?: AssistantTaskCatalogV1 | null;
  taskReason?: string | null;
  proposals?: AssistantProposalV1[]; proposalBusy?: string | null; reviewInvalidated?: string[];
  reviewAvailability?: Record<string, AssistantReviewV1["apply"]>;
  reviewActions?: Record<string, AssistantCapabilityReviewV1["action"]>;
  settings: AgentSettings | null; capabilities: AgentCapabilities | null; flags: AgentFlags;
  conversations: AgentConversationPage["items"][number][]; conversationCursor: string | null; conversationId: string | null; messages: AgentMessage[];
  messageCursor: string | null; sources: AgentWebSource[]; findings: AgentFinding[]; run: AgentRun | null;
  receipts: AgentEditReceipt[]; activity: AgentEvent[]; partial: string; partialTruncated: boolean;
  draft: string; submitting: boolean; pendingSend: boolean; error: string | null; loading?: string | null;
};
export type AssistantEditor = { sessionId: string; reviewStamp?: () => number; apply: (batchId: string, api: PreparedApi) => Promise<void>;
  applyAction?: (key: string, api: PreparedActionApi) => Promise<void> };
export type TurnBaseline = () => Promise<{ response: RichProjectResponse; scope: AgentRunRequest["scope"]; selectionContext?: AgentRunRequest["selectionContext"];
  historyOffers?: Pick<AgentHistoryOffer, "undo" | "redo">;
  historyTargets?: Pick<AssistantHistoryOfferV1, "undoBackend" | "redoBackend"> }>;
export type AssistantApi = Pick<AgentBrowserApi, "projectId" | "settings" | "saveSettings" | "capabilities" | "conversations" | "conversation" |
  "messages" | "resources" | "open" | "renew" | "close" | "submit" | "read" | "cancel" | "events" | "prepared">
  & Partial<Pick<AgentBrowserApi, "access" | "setAccess" | "offerHistory" | "offerReviewedHistory" | "tasks" | "checkMessage" | "proposals" | "proposal" | "discardProposal" | "reviewed" | "cancelApplication" | "retryApplication" | "reviewedAction" | "cancelAction" | "retryAction">>;
const pause = (milliseconds: number) => new Promise<void>(resolve => { setTimeout(resolve, milliseconds); });
function code(error: unknown): string { return error instanceof AgentApiFailure || error instanceof RichApiFailure ? error.code : error instanceof Error && error.message.startsWith("AGENT_") ? error.message : "REQUEST_FAILED"; }

export class AssistantController {
  view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: true }, conversations: [],
    conversationCursor: null, conversationId: null, messages: [], messageCursor: null, sources: [], findings: [], run: null, receipts: [], activity: [],
    partial: "", partialTruncated: false, draft: "", submitting: false, pendingSend: false, error: null };
  private owner: AgentOwner | null = null;
  private beat: ReturnType<typeof setTimeout> | null = null;
  private stream: AbortController | null = null;
  private closed = false;
  private epoch = 0;
  private sendEpoch = 0;
  private sequence = 0;
  private metadataEpoch = 0;
  private catalogEpoch = 0;
  private proposalEpoch = 0;
  private reviewIntentEpoch = 0;
  private reviewAcceptance: AssistantAcceptanceV1 | null = null;
  private reviewAction = false;
  private readonly reviewStamps = new Map<string, number>();
  private accessRevision = 1;
  private pending: AgentRunRequest | null = null;
  private readonly applying = new Set<string>();
  private readonly drafts = new Map<string, string>();
  private pendingBackground: JobAgentRequestV1 | null = null;
  private backgroundSequence = 0;
  private unsubscribeBackground: (() => void) | null = null;
  private readonly backgroundConversations = new Map<string, { cursor: number; generation: number; conversation: BackgroundConversation }>();
  constructor(readonly api: AssistantApi, private readonly editor: AssistantEditor,
    private readonly changed: (view: AssistantView) => void, private readonly heartbeatMs = 5000, private readonly jobs: ProjectJobs | null = null) {
    if (jobs) this.unsubscribeBackground = jobs.subscribe(() => { void this.reloadBackground().catch(error => this.publish({ error: code(error) })); });
  }

  get active(): boolean { return this.view.submitting || this.view.pendingSend || this.applying.size > 0 || this.view.run !== null && !terminal(this.view.run); }
  private publish(update: Partial<AssistantView>): void {
    if (this.closed) return;
    this.view = { ...this.view, ...update }; this.changed(this.view);
  }
  private readonly waiting = new Map<symbol, string>();
  private async wait<T>(label: string, work: () => Promise<T>): Promise<T> {
    const key = Symbol(); this.waiting.set(key, label); this.publish({ loading: label });
    try { return await work(); }
    finally { this.waiting.delete(key); this.publish({ loading: [...this.waiting.values()].at(-1) ?? null }); }
  }
  draft(value: string): void { this.publish({ draft: value, taskReason: null, ...(this.view.taskReason ? { error: null } : {}) }); }
  flags(value: AgentFlags): void {
    if (!this.api.setAccess) { this.publish({ flags: { ...value } }); return; }
    this.publish({ submitting: true, loading: "Обновляем разрешение на правки" });
    void this.api.setAccess(this.accessRevision, !value.allowEdits).then(access => {
      this.accessRevision = access.revision;
      this.publish({ flags: { ...value, allowEdits: !access.readOnly }, error: null });
    }).catch(error => this.publish({ error: code(error) }))
      .finally(() => { this.publish({ submitting: false, loading: null }); void this.refresh().catch(error => this.publish({ error: code(error) })); });
  }

  async refresh(): Promise<void> { return this.wait("Обновляем подключение и диалоги", () => this.refreshWork()); }
  async refreshCatalog(): Promise<void> {
    if (!this.api.tasks || this.closed) return;
    const epoch = ++this.catalogEpoch, flags = { ...this.view.flags };
    try {
      const taskCatalog = await this.api.tasks(flags);
      if (epoch === this.catalogEpoch && flags.allowEdits === this.view.flags.allowEdits && flags.allowWeb === this.view.flags.allowWeb)
        this.publish({ taskCatalog });
    } catch (error) {
      if (epoch === this.catalogEpoch) this.publish({ taskCatalog: null, error: code(error) });
    }
  }
  reviewChanged(): void {
    const stamp = this.editor.reviewStamp?.();
    if (stamp === undefined) return;
    const previous = this.view.reviewInvalidated ?? [], invalidated = new Set(previous);
    for (const [key, captured] of this.reviewStamps) if (captured !== stamp) invalidated.add(key);
    if (invalidated.size !== previous.length) this.publish({ reviewInvalidated: [...invalidated] });
  }
  async refreshProposals(): Promise<void> {
    if (!this.api.proposals || !this.view.taskCatalog?.protocolEnabled || this.closed) return;
    const epoch = ++this.proposalEpoch, stamp = this.editor.reviewStamp?.();
    const reply = await this.api.proposals();
    if (this.closed || epoch !== this.proposalEpoch) return;
    if (reply.projectId !== this.api.projectId) throw new AgentApiFailure("INVALID_RESULT");
    const proposals = reply.reviews.map(item => item.proposal);
    for (const proposal of proposals) if (!this.reviewStamps.has(proposalKey(proposal)) && stamp !== undefined)
      this.reviewStamps.set(proposalKey(proposal), stamp);
    this.publish({ proposals, reviewAvailability: Object.fromEntries(reply.reviews.map(item => [proposalKey(item.proposal), item.apply])),
      reviewActions: Object.fromEntries(reply.reviews.map(item => [proposalKey(item.proposal), item.action])) }); this.reviewChanged();
    if (!this.owner && this.view.flags.allowEdits && proposals.some(item => item.state === "ready" || item.state === "failed_before_commit")) {
      await this.ensureOwner(); await this.refreshCatalog();
      await this.refreshProposals();
    }
  }
  async applyProposal(displayed: AssistantProposalV1): Promise<void> {
    const key = proposalKey(displayed);
    this.reviewChanged();
    if (this.active || this.view.proposalBusy || !this.api.reviewed || !this.api.proposal
      || !this.view.taskCatalog?.protocolEnabled || !this.view.flags.allowEdits || !["ready", "failed_before_commit"].includes(displayed.state)
      || this.view.reviewInvalidated?.includes(key) || !this.view.proposals?.some(item => proposalKey(item) === key && ["ready", "failed_before_commit"].includes(item.state))) return;
    const epoch = ++this.reviewIntentEpoch;
    const acceptanceId = crypto.randomUUID();
    this.applying.add(key); this.publish({ proposalBusy: key, error: null });
    try {
      const owner = await this.ensureOwner(); await this.refreshCatalog();
      const current = await this.api.proposal(proposalRequest(displayed));
      this.reviewChanged();
      if (this.closed || epoch !== this.reviewIntentEpoch) return;
      if (proposalKey(current.proposal) !== key || !["ready", "failed_before_commit"].includes(current.proposal.state) || this.view.reviewInvalidated?.includes(key))
        throw new AgentApiFailure("AGENT_STALE_READ");
      if (!this.view.flags.allowEdits || current.apply.state !== "available") throw new AgentApiFailure(current.apply.reasonCode ?? "AGENT_TOOL_DENIED");
      const accepted = { ...proposalRequest(displayed), owner, acceptanceId };
      this.reviewAcceptance = accepted;
      this.reviewAction = !!current.action;
      if (current.proposal.state === "failed_before_commit") {
        const retryPort = current.action ? this.api.retryAction?.bind(this.api) : this.api.retryApplication?.bind(this.api);
        if (!retryPort) throw new AgentApiFailure("AGENT_PROTOCOL");
        const retry = await retryPort(accepted);
        if (proposalKey(retry) !== key || retry.state !== "ready") throw new AgentApiFailure("AGENT_STALE_READ");
        if (this.closed || epoch !== this.reviewIntentEpoch || !this.view.flags.allowEdits) return;
      }
      if (current.action) {
        if (!this.editor.applyAction || !this.api.reviewedAction) throw new AgentApiFailure("AGENT_PROTOCOL");
        await this.editor.applyAction(`${key}:${acceptanceId}`, this.api.reviewedAction(accepted));
      } else await this.editor.apply(`${key}:${acceptanceId}`, this.api.reviewed(accepted));
    } catch (error) { this.publish({ error: code(error) }); }
    finally { this.reviewAcceptance = null; this.reviewAction = false; this.applying.delete(key); this.publish({ proposalBusy: null }); await this.refreshProposals().catch(error => this.publish({ error: code(error) })); }
  }
  async discardProposal(displayed: AssistantProposalV1): Promise<void> {
    if (this.active || this.view.proposalBusy || !this.api.discardProposal || !this.view.taskCatalog?.protocolEnabled) return;
    const key = proposalKey(displayed); this.publish({ proposalBusy: key, error: null });
    try { await this.api.discardProposal(proposalRequest(displayed)); await this.refreshProposals(); }
    catch (error) { this.publish({ error: code(error) }); }
    finally { this.publish({ proposalBusy: null }); }
  }
  private async checkMessage(message: string): Promise<void> {
    if (!this.view.taskCatalog?.protocolEnabled) return;
    if (!this.api.checkMessage) throw new AgentApiFailure("AGENT_PROTOCOL");
    const result = await this.api.checkMessage(message, this.view.flags);
    if (result.availability.state !== "available") {
      this.publish({ taskReason: [result.availability.reason, result.availability.remedy].filter(Boolean).join(" ") });
      throw new AgentApiFailure(result.availability.reasonCode ?? "AGENT_TOOL_DENIED");
    }
  }
  private async refreshWork(): Promise<void> {
    const epoch = ++this.metadataEpoch;
    const access = await this.api.access?.();
    if (access && epoch === this.metadataEpoch) {
      this.accessRevision = access.revision;
      this.publish({ flags: { ...this.view.flags, allowEdits: !access.readOnly } });
    }
    const catalogEpoch = ++this.catalogEpoch;
    const [settings, capabilities, conversations, taskCatalog] = await Promise.all([this.api.settings(), this.api.capabilities(this.view.flags), this.api.conversations(), this.api.tasks?.(this.view.flags) ?? null]);
    if (epoch === this.metadataEpoch) this.publish({ settings, capabilities, conversations: conversations.items, conversationCursor: conversations.nextCursor });
    if (catalogEpoch === this.catalogEpoch) this.publish({ taskCatalog });
    await this.refreshProposals();
  }
  async init(): Promise<void> { return this.wait("Открываем помощника", () => this.initialize()); }
  private async initialize(): Promise<void> {
    try {
      await this.refresh();
      if (!this.closed && !this.view.conversationId && this.view.conversations.length) {
        const id = this.view.conversations[0]?.id;
        if (id) await this.select(id);
      }
    } catch (error) { this.publish({ error: code(error) }); }
  }
  async chooseModel(model: string | null, enabled = this.view.settings?.enabled ?? false): Promise<void> {
    return this.wait("Сохраняем модель помощника", () => this.chooseModelWork(model, enabled));
  }
  private async chooseModelWork(model: string | null, enabled: boolean): Promise<void> {
    const settings = this.view.settings;
    if (!settings) return;
    try {
      const next = await this.api.saveSettings({ expectedRevision: settings.revision, enabled, selectedAgentModel: model });
      this.publish({ settings: next, error: null }); await this.refresh();
      if (!enabled && this.view.run) {
        if (this.jobs) await this.reloadBackground();
        else { this.publish({ run: (await this.api.read(this.view.run.id)).run }); await this.reloadMessages(); }
      }
    } catch (error) { this.publish({ error: code(error) }); await this.refresh().catch(() => {}); }
  }
  private scheduleBeat(): void {
    if (this.beat) clearTimeout(this.beat);
    if (this.closed || !this.owner) return;
    this.beat = setTimeout(() => {
      const owner = this.owner;
      if (!owner || this.closed) return;
      void this.api.renew(owner).then(lease => {
        if (this.closed || this.owner !== owner) return;
        this.owner = lease.owner; this.scheduleBeat();
      }).catch(error => {
        this.publish({ error: code(error) }); this.stream?.abort(); this.owner = null;
        const runId = this.view.run?.id, epoch = this.epoch;
        void this.api.close(owner).then(async () => {
          if (!runId || this.closed || epoch !== this.epoch) return;
          const read = await this.api.read(runId);
          if (epoch === this.epoch) { this.publish({ run: read.run, receipts: read.receipts }); await this.reloadMessages(); }
        }).catch(error => this.publish({ error: code(error) }));
      });
    }, this.heartbeatMs);
  }
  private async ensureOwner(): Promise<AgentOwner> {
    if (!this.owner) this.owner = (await this.api.open(this.editor.sessionId)).owner;
    if (this.closed) { await this.api.close(this.owner); this.owner = null; throw new AgentApiFailure("AGENT_INTERRUPTED"); }
    this.scheduleBeat(); return this.owner;
  }
  private async ensureConversation(): Promise<string> {
    if (this.view.conversationId) return this.view.conversationId;
    const conversation = await this.api.conversation();
    this.publish({ conversationId: conversation.id, messages: [], sources: [], findings: [], messageCursor: null });
    return conversation.id;
  }
  async newConversation(): Promise<void> { return this.wait("Создаём диалог", () => this.newConversationWork()); }
  private async newConversationWork(): Promise<void> {
    if (this.view.submitting) throw new AgentApiFailure("AGENT_BUSY");
    if (this.active && !this.jobs) await this.stop();
    if (this.applying.size) throw new AgentApiFailure("AGENT_BUSY");
    this.drafts.set(this.view.conversationId ?? "", this.view.draft);
    const conversation = await this.api.conversation();
    ++this.epoch; this.stream?.abort(); this.sequence = 0;
    this.publish({ conversationId: conversation.id, messages: [], messageCursor: null, sources: [], findings: [], run: null,
      receipts: [], activity: [], partial: "", partialTruncated: false, draft: "", error: null });
    await this.refresh();
  }
  async select(id: string): Promise<void> { return this.wait("Открываем диалог", () => this.selectWork(id)); }
  private async selectWork(id: string): Promise<void> {
    if (id === this.view.conversationId) return;
    if (this.view.submitting) throw new AgentApiFailure("AGENT_BUSY");
    if (this.active && !this.jobs) await this.stop();
    if (this.applying.size) throw new AgentApiFailure("AGENT_BUSY");
    this.drafts.set(this.view.conversationId ?? "", this.view.draft);
    const epoch = ++this.epoch; this.stream?.abort(); this.sequence = 0;
    const page = await this.api.messages(id);
    if (this.closed || epoch !== this.epoch) return;
    this.publish({ conversationId: id, messages: page.items, messageCursor: page.nextCursor, sources: [], findings: [], run: null,
      receipts: [], activity: [], partial: "", partialTruncated: false, draft: this.drafts.get(id) ?? "", error: null });
    if (this.jobs) await this.reloadBackground();
  }
  async older(): Promise<void> { return this.wait("Загружаем предыдущие сообщения", () => this.olderWork()); }
  private async olderWork(): Promise<void> {
    const id = this.view.conversationId, cursor = this.view.messageCursor, epoch = this.epoch;
    if (!id || !cursor) return;
    const page = await this.api.messages(id, cursor);
    if (epoch !== this.epoch || this.closed) return;
    const known = new Set(this.view.messages.map(message => message.id));
    this.publish({ messages: [...page.items.filter(message => !known.has(message.id)), ...this.view.messages], messageCursor: page.nextCursor });
  }
  async moreConversations(): Promise<void> { return this.wait("Загружаем диалоги", () => this.moreConversationsWork()); }
  private async moreConversationsWork(): Promise<void> {
    const cursor = this.view.conversationCursor;
    if (!cursor) return;
    const page = await this.api.conversations(cursor), known = new Set(this.view.conversations.map(item => item.id));
    const items = [...this.view.conversations, ...page.items.filter(item => !known.has(item.id))];
    // Each response is bounded; the visible selector may contain several pages.
    this.publish({ conversations: items, conversationCursor: page.nextCursor });
  }
  async resource(kind: "sources" | "findings", id: string): Promise<void> { return this.wait("Открываем результат", () => this.resourceWork(kind, id)); }
  private async resourceWork(kind: "sources" | "findings", id: string): Promise<void> {
    if (this.jobs) { await this.reloadBackground(); if (this.view[kind].some(item => item.id === id)) return; }
    const conversation = this.view.conversationId, epoch = this.epoch;
    if (!conversation) return;
    const value = await this.api.resources(conversation, kind, [id]);
    if (epoch !== this.epoch || this.closed) return;
    if (kind === "sources") this.publish({ sources: [...this.view.sources.filter(source => !value.sources.some(item => item.id === source.id)), ...value.sources] });
    else this.publish({ findings: [...this.view.findings.filter(finding => !value.findings.some(item => item.id === finding.id)), ...value.findings] });
  }
  async send(baseline: TurnBaseline): Promise<void> {
    if (this.closed || this.view.submitting || this.view.run && !terminal(this.view.run) || this.applying.size) return;
    const message = this.view.draft;
    let flags = { ...this.view.flags };
    if (!message.trim() || [...message].length > 8000) return;
    if (this.jobs) { await this.sendBackground(baseline); return; }
    const epoch = ++this.sendEpoch;
    const currentSend = () => { if (this.closed || epoch !== this.sendEpoch) throw new AgentApiFailure("AGENT_CANCELLED"); };
    this.publish({ submitting: true, error: null });
    try {
      let request = this.pending;
      if (request && request.message !== message) throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      if (!request) {
        await this.refresh();
        currentSend();
        await this.checkMessage(message); currentSend();
        flags = { ...this.view.flags };
        if (!this.view.capabilities?.ready || !this.view.settings) throw new AgentApiFailure(this.view.capabilities?.unavailable?.code ?? "AGENT_CONNECTION_UNAVAILABLE");
        const settingsRevision = this.view.settings.revision;
        const owner = await this.ensureOwner(); currentSend();
        const conversationId = await this.ensureConversation(); currentSend();
        const current = await baseline(), workspace = current.response.workspace;
        currentSend();
        if (!workspace.project) throw new AgentApiFailure("AGENT_NOT_FOUND");
        const clientRequestId = crypto.randomUUID();
        if (this.view.taskCatalog?.protocolEnabled && this.api.offerReviewedHistory && current.historyOffers) await this.api.offerReviewedHistory({
          schemaVersion: 1, protocolVersion: 1, requestId: clientRequestId, ...current.historyTargets, offer: { owner,
            projectRevision: workspace.projectRevision, documentRevision: workspace.documentRevision,
            factsRevision: workspace.project.facts.revision, ...current.historyOffers } });
        else if (flags.allowEdits && current.historyOffers && this.api.offerHistory) await this.api.offerHistory({ owner,
          projectRevision: workspace.projectRevision, documentRevision: workspace.documentRevision,
          factsRevision: workspace.project.facts.revision, ...current.historyOffers });
        currentSend();
        request = { clientRequestId, conversationId, owner, message, ...flags, scope: current.scope,
          selectionContext: current.selectionContext ?? null,
          settingsRevision, projectRevision: workspace.projectRevision,
          documentRevision: workspace.documentRevision, factsRevision: workspace.project.facts.revision };
        this.pending = request;
      }
      currentSend();
      const run = await this.api.submit(request, this.view.taskCatalog?.protocolEnabled ?? false);
      if (this.closed || epoch !== this.sendEpoch) {
        if (!terminal(run)) await this.api.cancel(run.id, request.owner).catch(() => {});
        return;
      }
      this.pending = null; this.sequence = 0;
      this.publish({ run, draft: "", partial: "", partialTruncated: false, activity: [], receipts: [], pendingSend: false });
      if (!terminal(run)) {
        if (!this.owner || this.owner.epoch !== run.ownerEpoch) throw new AgentApiFailure("AGENT_OWNER_MISMATCH");
        this.startStream(run, this.owner);
      }
      await this.reloadMessages();
    } catch (error) {
      if (this.closed || epoch !== this.sendEpoch) return;
      if (error instanceof AgentApiFailure && error.status >= 400 && error.status < 500) this.pending = null;
      this.publish({ error: code(error), pendingSend: this.pending !== null });
    } finally { this.publish({ submitting: false }); }
  }
  private async reloadMessages(): Promise<void> {
    if (this.jobs) { await this.reloadBackground(); return; }
    const id = this.view.conversationId, epoch = this.epoch;
    if (!id) return;
    const page = await this.api.messages(id);
    if (!this.closed && epoch === this.epoch) this.publish({ messages: page.items, messageCursor: page.nextCursor });
    await this.refreshProposals();
  }
  private async sendBackground(baseline: TurnBaseline): Promise<void> {
    const jobs = this.jobs; if (!jobs) return;
    const epoch = ++this.sendEpoch;
    const currentSend = () => { if (this.closed || epoch !== this.sendEpoch) throw new AgentApiFailure("AGENT_CANCELLED"); };
    this.publish({ submitting: true, error: null });
    try {
      let pending = this.pendingBackground;
      if (pending && pending.request.message !== this.view.draft) throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      if (!pending) {
        await this.refresh(); currentSend(); await jobs.refresh(); currentSend();
        await this.checkMessage(this.view.draft); currentSend();
        const project = jobs.view.project, settings = this.view.settings;
        if (!project || !settings || !this.view.capabilities?.ready) throw new AgentApiFailure(this.view.capabilities?.unavailable?.code ?? "AGENT_CONNECTION_UNAVAILABLE");
        const conversationId = await this.ensureConversation(); currentSend();
        const current = await baseline(), workspace = current.response.workspace; currentSend();
        if (!workspace.project || this.closed) throw new AgentApiFailure("AGENT_STALE_READ");
        const clientRequestId = crypto.randomUUID();
        if (this.view.taskCatalog?.protocolEnabled && this.api.offerReviewedHistory && current.historyOffers) {
          const owner = await this.ensureOwner(); currentSend();
          await this.api.offerReviewedHistory({ schemaVersion: 1, protocolVersion: 1, requestId: clientRequestId,
            ...current.historyTargets, offer: { owner, projectRevision: workspace.projectRevision,
              documentRevision: workspace.documentRevision, factsRevision: workspace.project.facts.revision, ...current.historyOffers } });
          currentSend();
        }
        pending = { schemaVersion: 1, lineage: project.lineage, requestEpoch: project.requestEpoch,
          request: { clientRequestId, conversationId, message: this.view.draft, ...this.view.flags,
            scope: current.scope, selectionContext: current.selectionContext ?? null, settingsRevision: settings.revision, projectRevision: workspace.projectRevision,
            documentRevision: workspace.documentRevision, factsRevision: workspace.project.facts.revision } };
        this.pendingBackground = pending;
      }
      currentSend();
      const job = await jobs.submit(pending, this.view.taskCatalog?.protocolEnabled ?? false);
      if (this.closed || epoch !== this.sendEpoch) { await jobs.stop(job.id); return; }
      this.pendingBackground = null;
      this.publish({ draft: "", pendingSend: false }); await this.reloadBackground();
    } catch (error) {
      if (this.closed || epoch !== this.sendEpoch) return;
      if ((error instanceof AgentApiFailure || error instanceof RichApiFailure) && error.status >= 400 && error.status < 500) this.pendingBackground = null;
      this.publish({ error: code(error), pendingSend: this.pendingBackground !== null });
    } finally { this.publish({ submitting: false }); }
  }
  private async reloadBackground(): Promise<void> {
    const jobs = this.jobs, project = jobs?.view.project;
    if (!jobs || !project || this.closed) return;
    const sequence = ++this.backgroundSequence, epoch = this.epoch;
    const values = await Promise.all(project.jobs.filter(job => job.submission.kind === "agent").map(async job => {
      const old = this.backgroundConversations.get(job.id);
      if (old?.cursor === job.eventCursor && old.generation === job.executionGeneration) return { job, conversation: old.conversation };
      const conversation = await jobs.api.conversation(job.id);
      if (conversation.projectId !== this.api.projectId || !conversation.runs.some(run => run.id === job.id && run.ownerEpoch === job.executionGeneration)) throw new AgentApiFailure("INVALID_RESULT");
      const current = this.backgroundConversations.get(job.id);
      if (!current || current.generation < job.executionGeneration || current.generation === job.executionGeneration && current.cursor <= job.eventCursor)
        this.backgroundConversations.set(job.id, { cursor: job.eventCursor, generation: job.executionGeneration, conversation });
      return { job, conversation };
    }));
    if (this.closed || epoch !== this.epoch || sequence !== this.backgroundSequence) return;
    const summaries = new Map(this.view.conversations.map(item => [item.id, item]));
    const scoped = values.map(({ job, conversation }) => ({ conversation,
      run: conversation.runs.find(run => run.id === job.id && run.ownerEpoch === job.executionGeneration) }));
    for (const { conversation } of scoped) {
      const active = scoped.find(item => item.conversation.id === conversation.id && item.run && !terminal(item.run))?.run;
      summaries.set(conversation.id, { id: conversation.id, createdAt: conversation.createdAt, updatedAt: conversation.updatedAt,
        title: summaries.get(conversation.id)?.title ?? conversation.messages.find(message => message.role === "user")?.text.slice(0, 80) ?? "Новая беседа",
        activeRunId: active?.id ?? null });
    }
    const selected = scoped.filter(value => value.conversation.id === this.view.conversationId);
    const messages = new Map(this.view.messages.map(message => [message.id, message]));
    const sources = new Map(this.view.sources.map(source => [source.id, source])), findings = new Map(this.view.findings.map(finding => [finding.id, finding]));
    const runs = new Map<string, AgentRun>();
    for (const { conversation, run } of selected) {
      if (!run) continue;
      conversation.messages.filter(message => message.runId === run.id).forEach(message => messages.set(message.id, message));
      conversation.sources.filter(source => source.runId === run.id).forEach(source => sources.set(source.id, source));
      conversation.findings.filter(finding => finding.runId === run.id).forEach(finding => findings.set(finding.id, finding));
      runs.set(run.id, run);
    }
    const latest = [...runs.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt)).at(-1);
    this.publish({ conversations: [...summaries.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
      messages: [...messages.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)), sources: [...sources.values()], findings: [...findings.values()],
      activity: project.jobs.find(job => job.id === latest?.id)?.activity ?? [], run: latest ?? null, error: jobs.view.error });
    await this.refreshProposals();
  }
  private startStream(run: AgentRun, owner: AgentOwner): void {
    this.stream?.abort(); const stream = new AbortController(); this.stream = stream;
    const epoch = this.epoch;
    void this.consume(run.id, owner, stream, epoch).catch(error => this.publish({ error: code(error) }));
  }
  private async consume(runId: string, owner: AgentOwner, stream: AbortController, epoch: number): Promise<void> {
    let failures = 0;
    while (!this.closed && !stream.signal.aborted && epoch === this.epoch) {
      try {
        for await (const event of this.api.events(runId, owner, this.sequence, stream.signal)) {
          if (this.closed || stream.signal.aborted || epoch !== this.epoch) return;
          if (event.projectId !== this.api.projectId || event.runId !== runId || event.conversationId !== this.view.conversationId) throw new AgentApiFailure("INVALID_RESULT");
          if (event.sequence <= this.sequence) continue;
          if (event.sequence !== this.sequence + 1) throw new AgentApiFailure("AGENT_RESYNC_REQUIRED");
          this.sequence = event.sequence; failures = 0;
          this.accept(event);
        }
        if (stream.signal.aborted || this.closed || epoch !== this.epoch) return;
        const read = await this.api.read(runId);
        this.publish({ run: read.run, receipts: read.receipts });
        if (terminal(read.run)) { await this.reloadMessages(); this.publish({ partial: "" }); return; }
      } catch (error) {
        if (stream.signal.aborted || this.closed || epoch !== this.epoch) return;
        if (error instanceof AgentApiFailure && error.code === "AGENT_RESYNC_REQUIRED") {
          const read = await this.api.read(runId);
          this.publish({ run: read.run, receipts: read.receipts }); await this.reloadMessages();
          if (terminal(read.run)) return;
          this.sequence = 0;
        }
        if (++failures >= 3) { this.publish({ error: code(error) }); await this.stop(); return; }
      }
      await pause(250 * Math.max(1, failures));
    }
  }
  private accept(event: AgentEvent): void {
    const activity = event.type === "activity.updated" ? this.view.activity.filter(item => item.type !== "activity.updated" || item.payload.itemId !== event.payload.itemId) : this.view.activity;
    const update: Partial<AssistantView> = { activity: event.type === "message.delta" ? activity : [...activity, event].slice(-40) };
    if (event.type === "message.delta") {
      const raw = new TextEncoder().encode(this.view.partial + event.payload.text);
      update.partial = new TextDecoder("utf-8", { fatal: true }).decode(raw.slice(0, 65536), { stream: true });
      update.partialTruncated = raw.length > 65536 || this.view.partialTruncated;
    } else if (event.type === "run.state_changed" && this.view.run) {
      update.run = { ...this.view.run, state: event.payload.state, error: event.payload.error,
        savedBatchId: event.payload.savedBatchId, outcomeUnknown: event.payload.outcomeUnknown,
        finishedAt: ["completed", "failed", "cancelled", "interrupted"].includes(event.payload.state) ? event.timestamp : null };
    } else if (event.type === "source.ready" || event.type === "finding.ready") {
      void this.resource(event.type === "source.ready" ? "sources" : "findings", event.payload.id).catch(error => this.publish({ error: code(error) }));
    } else if (event.type === "edit.result") {
      const epoch = this.epoch;
      void this.api.read(event.runId).then(read => { if (epoch === this.epoch) this.publish({ receipts: read.receipts }); }).catch(error => this.publish({ error: code(error) }));
    } else if (event.type === "edit.offered") {
      void this.refreshProposals().catch(error => this.publish({ error: code(error) }));
    }
    this.publish(update);
  }
  async stop(): Promise<void> { return this.wait("Останавливаем задачу", () => this.stopWork()); }
  private async stopWork(): Promise<void> {
    ++this.sendEpoch;
    ++this.reviewIntentEpoch;
    const acceptance = this.reviewAcceptance;
    if (acceptance) {
      if (this.reviewAction) {
        if (!this.api.cancelAction) throw new AgentApiFailure("AGENT_PROTOCOL");
        await this.api.cancelAction(acceptance);
      } else {
        if (!this.api.cancelApplication) throw new AgentApiFailure("AGENT_PROTOCOL");
        await this.api.cancelApplication(acceptance);
      }
    }
    if (this.jobs) {
      if (this.view.run && !terminal(this.view.run)) await this.jobs.stop(this.view.run.id);
      this.pendingBackground = null; this.publish({ pendingSend: false }); await this.reloadBackground(); return;
    }
    this.stream?.abort();
    const run = this.view.run, owner = this.owner;
    if (run && !terminal(run) && owner) {
      const cancelled = await this.api.cancel(run.id, owner);
      this.publish({ run: cancelled });
      const deadline = Date.now() + 5500;
      while (!this.closed && Date.now() < deadline) {
        const value = await this.api.read(run.id);
        this.publish({ run: value.run, receipts: value.receipts });
        if (terminal(value.run)) { await this.reloadMessages(); this.publish({ partial: "" }); return; }
        await pause(50);
      }
      throw new AgentApiFailure("AGENT_CLEANUP_FAILED");
    }
    if (this.pending && owner) { await this.api.close(owner); this.owner = null; }
    this.pending = null; this.publish({ pendingSend: false });
  }
  close(): void {
    this.closed = true; ++this.epoch; ++this.sendEpoch; ++this.reviewIntentEpoch; ++this.proposalEpoch; this.stream?.abort();
    if (this.beat) clearTimeout(this.beat);
    this.unsubscribeBackground?.(); this.unsubscribeBackground = null;
    const owner = this.owner; this.owner = null;
    if (owner) void this.api.close(owner).catch(() => {});
  }
}
