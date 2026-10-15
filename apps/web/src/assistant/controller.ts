import type { AgentCapabilities } from "../contracts/generated/agent_capabilities";
import type { AgentSettings } from "../contracts/generated/agent_settings";
import type { AgentConversationPage } from "../contracts/generated/agent_conversation_page";
import type { AgentMessage } from "../contracts/generated/agent_message";
import type { AgentWebSource } from "../contracts/generated/agent_web_source";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import type { AgentRun } from "../contracts/generated/agent_run";
import type { AgentRunRequest } from "../contracts/generated/agent_run_request";
import type { AgentEditReceipt } from "../contracts/generated/agent_edit_receipt";
import type { AgentEvent } from "../contracts/generated/agent_event";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { AgentApiFailure, type AgentBrowserApi, type AgentFlags, type AgentOwner } from "./api";
import type { PreparedApi } from "./editor-bridge";

export const terminal = (run: AgentRun | null): boolean => run !== null && ["completed", "failed", "cancelled", "interrupted"].includes(run.state);
export type AssistantView = {
  settings: AgentSettings | null; capabilities: AgentCapabilities | null; flags: AgentFlags;
  conversations: AgentConversationPage["items"][number][]; conversationCursor: string | null; conversationId: string | null; messages: AgentMessage[];
  messageCursor: string | null; sources: AgentWebSource[]; findings: AgentFinding[]; run: AgentRun | null;
  receipts: AgentEditReceipt[]; activity: AgentEvent[]; partial: string; partialTruncated: boolean;
  draft: string; submitting: boolean; pendingSend: boolean; error: string | null;
};
export type AssistantEditor = { sessionId: string; apply: (batchId: string, api: PreparedApi) => Promise<void> };
export type TurnBaseline = () => Promise<{ response: RichProjectResponse; scope: AgentRunRequest["scope"] }>;
export type AssistantApi = Pick<AgentBrowserApi, "projectId" | "settings" | "saveSettings" | "capabilities" | "conversations" | "conversation" |
  "messages" | "resources" | "open" | "renew" | "close" | "submit" | "read" | "cancel" | "events" | "prepared">;
const pause = (milliseconds: number) => new Promise<void>(resolve => { setTimeout(resolve, milliseconds); });
function code(error: unknown): string { return error instanceof AgentApiFailure ? error.code : error instanceof Error && error.message.startsWith("AGENT_") ? error.message : "REQUEST_FAILED"; }

export class AssistantController {
  view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: true }, conversations: [],
    conversationCursor: null, conversationId: null, messages: [], messageCursor: null, sources: [], findings: [], run: null, receipts: [], activity: [],
    partial: "", partialTruncated: false, draft: "", submitting: false, pendingSend: false, error: null };
  private owner: AgentOwner | null = null;
  private beat: ReturnType<typeof setTimeout> | null = null;
  private stream: AbortController | null = null;
  private closed = false;
  private epoch = 0;
  private sequence = 0;
  private metadataEpoch = 0;
  private pending: AgentRunRequest | null = null;
  private readonly applying = new Set<string>();
  private readonly drafts = new Map<string, string>();
  constructor(readonly api: AssistantApi, private readonly editor: AssistantEditor,
    private readonly changed: (view: AssistantView) => void, private readonly heartbeatMs = 5000) {}

  get active(): boolean { return this.view.submitting || this.view.pendingSend || this.applying.size > 0 || this.view.run !== null && !terminal(this.view.run); }
  private publish(update: Partial<AssistantView>): void {
    if (this.closed) return;
    this.view = { ...this.view, ...update }; this.changed(this.view);
  }
  draft(value: string): void { this.publish({ draft: value }); }
  flags(value: AgentFlags): void { this.publish({ flags: { ...value } }); void this.refresh().catch(error => this.publish({ error: code(error) })); }

  async refresh(): Promise<void> {
    const epoch = ++this.metadataEpoch;
    const [settings, capabilities, conversations] = await Promise.all([this.api.settings(), this.api.capabilities(this.view.flags), this.api.conversations()]);
    if (epoch === this.metadataEpoch) this.publish({ settings, capabilities, conversations: conversations.items, conversationCursor: conversations.nextCursor });
  }
  async init(): Promise<void> {
    try {
      await this.refresh();
      if (!this.closed && !this.view.conversationId && this.view.conversations.length) {
        const id = this.view.conversations[0]?.id;
        if (id) await this.select(id);
      }
    } catch (error) { this.publish({ error: code(error) }); }
  }
  async chooseModel(model: string | null, enabled = this.view.settings?.enabled ?? false): Promise<void> {
    const settings = this.view.settings;
    if (!settings) return;
    try {
      const next = await this.api.saveSettings({ expectedRevision: settings.revision, enabled, selectedAgentModel: model });
      this.publish({ settings: next, error: null }); await this.refresh();
      if (!enabled && this.view.run) { this.publish({ run: (await this.api.read(this.view.run.id)).run }); await this.reloadMessages(); }
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
  async newConversation(): Promise<void> {
    if (this.view.submitting) throw new AgentApiFailure("AGENT_BUSY");
    if (this.active) await this.stop();
    if (this.applying.size) throw new AgentApiFailure("AGENT_BUSY");
    this.drafts.set(this.view.conversationId ?? "", this.view.draft);
    const conversation = await this.api.conversation();
    ++this.epoch; this.stream?.abort(); this.sequence = 0;
    this.publish({ conversationId: conversation.id, messages: [], messageCursor: null, sources: [], findings: [], run: null,
      receipts: [], activity: [], partial: "", partialTruncated: false, draft: "", error: null });
    await this.refresh();
  }
  async select(id: string): Promise<void> {
    if (id === this.view.conversationId) return;
    if (this.view.submitting) throw new AgentApiFailure("AGENT_BUSY");
    if (this.active) await this.stop();
    if (this.applying.size) throw new AgentApiFailure("AGENT_BUSY");
    this.drafts.set(this.view.conversationId ?? "", this.view.draft);
    const epoch = ++this.epoch; this.stream?.abort(); this.sequence = 0;
    const page = await this.api.messages(id);
    if (this.closed || epoch !== this.epoch) return;
    this.publish({ conversationId: id, messages: page.items, messageCursor: page.nextCursor, sources: [], findings: [], run: null,
      receipts: [], activity: [], partial: "", partialTruncated: false, draft: this.drafts.get(id) ?? "", error: null });
  }
  async older(): Promise<void> {
    const id = this.view.conversationId, cursor = this.view.messageCursor, epoch = this.epoch;
    if (!id || !cursor) return;
    const page = await this.api.messages(id, cursor);
    if (epoch !== this.epoch || this.closed) return;
    const known = new Set(this.view.messages.map(message => message.id));
    this.publish({ messages: [...page.items.filter(message => !known.has(message.id)), ...this.view.messages], messageCursor: page.nextCursor });
  }
  async moreConversations(): Promise<void> {
    const cursor = this.view.conversationCursor;
    if (!cursor) return;
    const page = await this.api.conversations(cursor), known = new Set(this.view.conversations.map(item => item.id));
    const items = [...this.view.conversations, ...page.items.filter(item => !known.has(item.id))];
    // Each response is bounded; the visible selector may contain several pages.
    this.publish({ conversations: items, conversationCursor: page.nextCursor });
  }
  async resource(kind: "sources" | "findings", id: string): Promise<void> {
    const conversation = this.view.conversationId, epoch = this.epoch;
    if (!conversation) return;
    const value = await this.api.resources(conversation, kind, [id]);
    if (epoch !== this.epoch || this.closed) return;
    if (kind === "sources") this.publish({ sources: [...this.view.sources.filter(source => !value.sources.some(item => item.id === source.id)), ...value.sources] });
    else this.publish({ findings: [...this.view.findings.filter(finding => !value.findings.some(item => item.id === finding.id)), ...value.findings] });
  }
  async send(baseline: TurnBaseline): Promise<void> {
    if (this.closed || this.view.submitting || this.view.run && !terminal(this.view.run) || this.applying.size) return;
    const message = this.view.draft, flags = { ...this.view.flags };
    if (!message.trim() || [...message].length > 8000) return;
    this.publish({ submitting: true, error: null });
    try {
      let request = this.pending;
      if (request && request.message !== message) throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      if (!request) {
        await this.refresh();
        if (!this.view.capabilities?.ready || !this.view.settings) throw new AgentApiFailure(this.view.capabilities?.unavailable?.code ?? "AGENT_CONNECTION_UNAVAILABLE");
        const settingsRevision = this.view.settings.revision;
        const owner = await this.ensureOwner(), conversationId = await this.ensureConversation();
        const current = await baseline(), workspace = current.response.workspace;
        if (this.closed) throw new AgentApiFailure("AGENT_INTERRUPTED");
        if (!workspace.project) throw new AgentApiFailure("AGENT_NOT_FOUND");
        request = { clientRequestId: crypto.randomUUID(), conversationId, owner, message, ...flags, scope: current.scope,
          settingsRevision, projectRevision: workspace.projectRevision,
          documentRevision: workspace.documentRevision, factsRevision: workspace.project.facts.revision };
        this.pending = request;
      }
      const run = await this.api.submit(request);
      this.pending = null; this.sequence = 0;
      this.publish({ run, draft: "", partial: "", partialTruncated: false, activity: [], receipts: [], pendingSend: false });
      if (!terminal(run)) {
        if (!this.owner || this.owner.epoch !== run.ownerEpoch) throw new AgentApiFailure("AGENT_OWNER_MISMATCH");
        this.startStream(run, this.owner);
      }
      await this.reloadMessages();
    } catch (error) {
      if (error instanceof AgentApiFailure && error.status >= 400 && error.status < 500) this.pending = null;
      this.publish({ error: code(error), pendingSend: this.pending !== null });
    } finally { this.publish({ submitting: false }); }
  }
  private async reloadMessages(): Promise<void> {
    const id = this.view.conversationId, epoch = this.epoch;
    if (!id) return;
    const page = await this.api.messages(id);
    if (!this.closed && epoch === this.epoch) this.publish({ messages: page.items, messageCursor: page.nextCursor });
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
          this.accept(event, owner);
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
  private accept(event: AgentEvent, owner: AgentOwner): void {
    const update: Partial<AssistantView> = { activity: [...this.view.activity, event].slice(-40) };
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
    } else if (event.type === "edit.offered" && !terminal(this.view.run) && !this.applying.has(event.payload.batchId)
      && !this.view.receipts.some(receipt => receipt.batchId === event.payload.batchId)) {
      const id = event.payload.batchId, epoch = this.epoch;
      this.applying.add(id);
      void this.editor.apply(id, this.api.prepared(event.runId, owner)).catch(error => {
        if (epoch === this.epoch) this.publish({ error: code(error) });
      }).finally(() => { this.applying.delete(id); this.publish({}); });
    }
    this.publish(update);
  }
  async stop(): Promise<void> {
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
    this.closed = true; ++this.epoch; this.stream?.abort();
    if (this.beat) clearTimeout(this.beat);
    const owner = this.owner; this.owner = null;
    if (owner) void this.api.close(owner).catch(() => {});
  }
}
