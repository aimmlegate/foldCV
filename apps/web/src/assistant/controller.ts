import type { AgentEvent } from "../contracts/generated/agent_event";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import type { AgentMessage } from "../contracts/generated/agent_message";
import type { AgentSettings } from "../contracts/generated/agent_settings";
import type { AgentWebSource } from "../contracts/generated/agent_web_source";
import type { AssistantApplyResultV1 } from "../contracts/generated/assistant_apply_result_v1";
import type { AssistantCapabilitiesV1 } from "../contracts/generated/assistant_capabilities_v1";
import type { AssistantConversationV1 } from "../contracts/generated/assistant_conversation_v1";
import type { AssistantFileV1 } from "../contracts/generated/assistant_file_v1";
import type { AssistantMessagesV1 } from "../contracts/generated/assistant_messages_v1";
import type { AssistantRunRequestV2 } from "../contracts/generated/assistant_run_request_v2";
import { AgentApiFailure, type AgentFlags, type AssistantApi, type Proposal, type Run } from "./api";

/** The assistant drawer's state on the /v2 routes (D109, plan 2.8): one long-poll loop per run, proposals that only
 * the user applies through the open editor, and the transcript of the selected conversation. */
// The message, source, finding and event models are shared with the run files; their own generated types keep the
// fields that the combined reply schema's conditional parts drop.
export type AssistantEvent = AgentEvent;
export type AssistantMessage = AgentMessage;
export type AssistantSource = AgentWebSource;
export type AssistantFinding = AgentFinding;
export type AssistantSelection = NonNullable<AssistantRunRequestV2["selection"]>;
export const terminal = (run: Run | null): boolean => run !== null && ["completed", "failed", "cancelled", "interrupted"].includes(run.state);
export type AssistantView = {
  settings: AgentSettings | null; capabilities: AssistantCapabilitiesV1 | null; flags: AgentFlags;
  conversations: AssistantConversationV1[]; conversationId: string | null; messages: AssistantMessage[];
  sources: AssistantSource[]; findings: AssistantFinding[]; files: AssistantFileV1[]; run: Run | null;
  activity: AssistantEvent[]; partial: string; partialTruncated: boolean;
  proposals: Proposal[]; proposalBusy: string | null; staleProposals: string[];
  draft: string; submitting: boolean; pendingSend: boolean; error: string | null; loading?: string | null;
};
/** The open editor: Apply goes through its token, flushes its typing first and adopts the committed result. */
export type AssistantEditor = {
  applyProposal: (proposalId: string, allowEdits: boolean) => Promise<AssistantApplyResultV1>;
  actionApplied?: (action: NonNullable<AssistantApplyResultV1["action"]>) => Promise<void>;
};
export type Port = Pick<AssistantApi, "projectId" | "settings" | "saveSettings" | "capabilities" | "conversations" |
  "createConversation" | "messages" | "submit" | "events" | "cancel" | "proposals" | "discard">;
type Pending = { conversationId: string; request: AssistantRunRequestV2 };
// The combined reply types each message as an open object (see above); the server validated it as an AgentMessage.
const messagesOf = (value: AssistantMessagesV1): AgentMessage[] => value.messages as unknown as AgentMessage[];
const pause = (milliseconds: number) => new Promise<void>(resolve => { setTimeout(resolve, milliseconds); });
function code(error: unknown): string {
  return error instanceof AgentApiFailure ? error.code : error instanceof Error && /^[A-Z][A-Z0-9_]+$/u.test(error.message) ? error.message : "REQUEST_FAILED";
}

export class AssistantController {
  view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: true }, conversations: [],
    conversationId: null, messages: [], sources: [], findings: [], files: [], run: null, activity: [], partial: "",
    partialTruncated: false, proposals: [], proposalBusy: null, staleProposals: [], draft: "", submitting: false,
    pendingSend: false, error: null };
  private closed = false;
  private epoch = 0;
  private sendEpoch = 0;
  private stream: AbortController | null = null;
  private following: Promise<void> | null = null;
  private pending: Pending | null = null;
  private readonly drafts = new Map<string, string>();
  // The whole conversation as last read; the transcript shows sources and findings as they arrive or are opened.
  private loaded: { sources: AssistantSource[]; findings: AssistantFinding[] } = { sources: [], findings: [] };

  constructor(readonly api: Port, private readonly editor: AssistantEditor, private readonly changed: (view: AssistantView) => void,
    private readonly retryMs = 250) {}

  get active(): boolean { return this.view.submitting || this.view.pendingSend || this.view.proposalBusy !== null || this.view.run !== null && !terminal(this.view.run); }
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
  draft(value: string): void { this.publish({ draft: value }); }
  /** The panel's two flags; they go with each run, and Apply sends the edits flag again. */
  flags(value: AgentFlags): void { this.publish({ flags: { ...value } }); }

  async init(): Promise<void> {
    return this.wait("Открываем помощника", async () => {
      try {
        await this.refreshWork();
        const id = this.view.conversations[0]?.id;
        if (!this.closed && !this.view.conversationId && id) await this.selectWork(id);
      } catch (error) { this.publish({ error: code(error) }); }
    });
  }
  async refresh(): Promise<void> { return this.wait("Обновляем подключение и диалоги", () => this.refreshWork()); }
  /** A quiet capability read: the connection check can finish after the panel opened, and nothing else re-reads it. */
  async refreshCapabilities(): Promise<void> {
    const capabilities = await this.api.capabilities();
    if (!this.closed) this.publish({ capabilities });
  }
  private async refreshWork(): Promise<void> {
    const [settings, capabilities, conversations] = await Promise.all([this.api.settings(), this.api.capabilities(), this.api.conversations()]);
    this.publish({ settings, capabilities, conversations: conversations.items });
    await this.refreshProposals();
  }
  async refreshProposals(): Promise<void> {
    const conversation = this.view.conversationId;
    const reply = await this.api.proposals();
    if (this.closed || conversation !== this.view.conversationId) return;
    this.publish({ proposals: reply.items.filter(item => item.conversationId === conversation) });
  }

  async chooseModel(model: string | null, enabled = this.view.settings?.enabled ?? false): Promise<void> {
    return this.wait("Сохраняем модель помощника", async () => {
      const settings = this.view.settings;
      if (!settings) return;
      try {
        const next = await this.api.saveSettings({ expectedRevision: settings.revision, enabled, selectedAgentModel: model });
        this.publish({ settings: next, error: null }); await this.refreshWork();
      } catch (error) { this.publish({ error: code(error) }); await this.refreshWork().catch(() => {}); }
    });
  }

  async newConversation(): Promise<void> {
    return this.wait("Создаём диалог", async () => {
      if (this.view.submitting || this.view.proposalBusy) throw new AgentApiFailure("AGENT_BUSY");
      if (this.view.run && !terminal(this.view.run)) await this.stopWork();
      this.drafts.set(this.view.conversationId ?? "", this.view.draft);
      const conversation = await this.api.createConversation();
      this.leaveConversation();
      this.loaded = { sources: [], findings: [] };
      this.publish({ conversationId: conversation.id, messages: [], sources: [], findings: [], files: [], run: null, activity: [],
        partial: "", partialTruncated: false, proposals: [], staleProposals: [], draft: "", error: null });
      await this.refreshWork();
    });
  }
  async select(id: string): Promise<void> { return this.wait("Открываем диалог", () => this.selectWork(id)); }
  private async selectWork(id: string): Promise<void> {
    if (id === this.view.conversationId) return;
    if (this.view.submitting || this.view.proposalBusy) throw new AgentApiFailure("AGENT_BUSY");
    if (this.view.run && !terminal(this.view.run)) await this.stopWork();
    this.drafts.set(this.view.conversationId ?? "", this.view.draft);
    const epoch = this.leaveConversation();
    const value = await this.api.messages(id);
    if (this.closed || epoch !== this.epoch) return;
    this.loaded = { sources: value.sources, findings: value.findings };
    const runs = [...value.runs], latest = runs.at(-1) ?? null;
    this.publish({ conversationId: id, messages: messagesOf(value), sources: [], findings: [], files: [...value.files ?? []],
      run: latest, activity: [], partial: "", partialTruncated: false, staleProposals: [], draft: this.drafts.get(id) ?? "", error: null });
    await this.refreshProposals();
    // A run of this conversation that is still going (for example after a reload) is followed again.
    if (latest && !terminal(latest)) this.follow(latest);
  }
  private leaveConversation(): number { this.stream?.abort(); this.stream = null; this.following = null; return ++this.epoch; }

  /** Show a stored source or finding of this conversation in the transcript. */
  async resource(kind: "sources" | "findings", id: string): Promise<void> {
    return this.wait("Открываем результат", async () => {
      if (!this.loadedHas(kind, id)) await this.reloadMessages();
      this.reveal(kind, id);
    });
  }
  private loadedHas(kind: "sources" | "findings", id: string): boolean { return this.loaded[kind].some(item => item.id === id); }
  private reveal(kind: "sources" | "findings", id: string): void {
    if (kind === "sources") {
      const found = this.loaded.sources.find(item => item.id === id);
      if (found) this.publish({ sources: [...this.view.sources.filter(item => item.id !== id), found] });
    } else {
      const found = this.loaded.findings.find(item => item.id === id);
      if (found) this.publish({ findings: [...this.view.findings.filter(item => item.id !== id), found] });
    }
  }
  private async reloadMessages(): Promise<void> {
    const id = this.view.conversationId, epoch = this.epoch;
    if (!id) return;
    const value = await this.api.messages(id);
    if (this.closed || epoch !== this.epoch) return;
    this.loaded = { sources: value.sources, findings: value.findings };
    const runs = [...value.runs], current = this.view.run ? runs.find(run => run.id === this.view.run?.id) : undefined;
    this.publish({ messages: messagesOf(value), files: [...value.files ?? []], ...(current ? { run: current } : {}) });
  }

  async send(selection: () => Promise<AssistantSelection | null> = () => Promise.resolve(null)): Promise<void> {
    if (this.closed || this.view.submitting || this.view.proposalBusy || this.view.run && !terminal(this.view.run)) return;
    const message = this.view.draft;
    if (!message.trim() || [...message].length > 8000) return;
    const epoch = ++this.sendEpoch;
    const current = () => { if (this.closed || epoch !== this.sendEpoch) throw new AgentApiFailure("AGENT_CANCELLED"); };
    this.publish({ submitting: true, error: null });
    try {
      let pending = this.pending;
      if (pending && pending.request.message !== message) pending = this.pending = null;
      if (!pending) {
        await this.refreshWork(); current();
        if (!this.view.capabilities?.ready) throw new AgentApiFailure(this.view.capabilities?.unavailable?.code ?? "AGENT_CONNECTION_UNAVAILABLE");
        const conversationId = this.view.conversationId ?? await this.openConversation(); current();
        const selected = await selection(); current();
        pending = { conversationId, request: { clientRequestId: crypto.randomUUID(), message, ...this.view.flags, selection: selected } };
        this.pending = pending;
      }
      // A retried send repeats the captured request: the server returns the run it already started.
      const run = await this.api.submit(pending.conversationId, pending.request);
      if (this.closed || epoch !== this.sendEpoch) { if (!terminal(run)) await this.api.cancel(run.id).catch(() => {}); return; }
      this.pending = null;
      this.publish({ run, draft: "", partial: "", partialTruncated: false, activity: [], pendingSend: false });
      await this.reloadMessages();
      if (!terminal(run)) this.follow(run);
    } catch (error) {
      if (this.closed || epoch !== this.sendEpoch) return;
      // A refusal is final; a lost reply or a server failure keeps the request for an exact retry.
      if (error instanceof AgentApiFailure && error.status >= 400 && error.status < 500) this.pending = null;
      this.publish({ error: code(error), pendingSend: this.pending !== null });
    } finally { this.publish({ submitting: false }); }
  }
  private async openConversation(): Promise<string> {
    const conversation = await this.api.createConversation();
    this.loaded = { sources: [], findings: [] };
    this.publish({ conversationId: conversation.id, messages: [], sources: [], findings: [], files: [], proposals: [], staleProposals: [] });
    return conversation.id;
  }

  /** One long-poll loop per run; it ends when the run ends, the conversation changes or the drawer closes. */
  private follow(run: Run): void {
    this.stream?.abort();
    const stream = new AbortController(), epoch = this.epoch;
    this.stream = stream;
    const work = (async () => {
      let after = 0, failures = 0;
      while (!this.closed && !stream.signal.aborted && epoch === this.epoch) {
        try {
          const reply = await this.api.events(run.id, after, stream.signal);
          if (this.closed || stream.signal.aborted || epoch !== this.epoch) return;
          if (reply.run.id !== run.id || reply.events.some(event => event.runId !== run.id)) throw new AgentApiFailure("INVALID_RESULT");
          failures = 0;
          for (const event of reply.events) if (event.sequence > after) this.accept(event);
          after = Math.max(after, reply.next);
          this.publish({ run: reply.run });
          if (terminal(reply.run)) {
            await this.reloadMessages(); await this.refreshProposals();
            this.publish({ partial: "" });
            return;
          }
        } catch (error) {
          if (this.closed || stream.signal.aborted || epoch !== this.epoch) return;
          if (++failures >= 3) { this.publish({ error: code(error) }); return; }
          await pause(this.retryMs * failures);
        }
      }
    })().catch(error => { this.publish({ error: code(error) }); });
    this.following = work;
  }
  private accept(event: AssistantEvent): void {
    const activity = event.type === "activity.updated" ? this.view.activity.filter(item => item.type !== "activity.updated" || item.payload.itemId !== event.payload.itemId) : this.view.activity;
    const update: Partial<AssistantView> = { activity: event.type === "message.delta" ? activity : [...activity, event].slice(-40) };
    if (event.type === "message.delta") {
      const raw = new TextEncoder().encode(this.view.partial + event.payload.text);
      update.partial = new TextDecoder("utf-8").decode(raw.slice(0, 65536), { stream: true });
      update.partialTruncated = raw.length > 65536 || this.view.partialTruncated;
    } else if (event.type === "source.ready" || event.type === "finding.ready") {
      const kind = event.type === "source.ready" ? "sources" : "findings", id = event.payload.id;
      void this.reloadMessages().then(() => { this.reveal(kind, id); }).catch(error => { this.publish({ error: code(error) }); });
    } else if (event.type === "file.ready") {
      void this.reloadMessages().catch(error => { this.publish({ error: code(error) }); });
    } else if (event.type === "proposal.ready") {
      void this.refreshProposals().catch(error => { this.publish({ error: code(error) }); });
    }
    this.publish(update);
  }

  /** Apply goes through the editor: it flushes typing, sends the panel's edits flag and adopts the committed result,
   * which is one undo action. A stale proposal stays a draft and shows the stale notice. */
  async applyProposal(proposal: Proposal): Promise<void> {
    if (this.closed || this.view.proposalBusy || proposal.state !== "draft") return;
    this.publish({ proposalBusy: proposal.id, error: null });
    try {
      const result = await this.editor.applyProposal(proposal.id, this.view.flags.allowEdits);
      this.publish({ proposals: this.view.proposals.map(item => item.id === result.proposal.id ? result.proposal : item) });
      if (result.action) await this.editor.actionApplied?.(result.action);
    } catch (error) {
      const failure = code(error);
      if (failure === "ASSISTANT_PROPOSAL_STALE") this.publish({ staleProposals: [...new Set([...this.view.staleProposals, proposal.id])] });
      this.publish({ error: failure });
    } finally {
      this.publish({ proposalBusy: null });
      await this.refreshProposals().catch(() => {});
    }
  }
  async discardProposal(proposal: Proposal): Promise<void> {
    if (this.closed || this.view.proposalBusy || proposal.state !== "draft") return;
    this.publish({ proposalBusy: proposal.id, error: null });
    try {
      const value = await this.api.discard(proposal.id);
      this.publish({ proposals: this.view.proposals.map(item => item.id === value.id ? value : item) });
    } catch (error) { this.publish({ error: code(error) }); }
    finally { this.publish({ proposalBusy: null }); }
  }

  async stop(): Promise<void> { return this.wait("Останавливаем задачу", () => this.stopWork()); }
  private async stopWork(): Promise<void> {
    ++this.sendEpoch;
    const run = this.view.run;
    if (run && !terminal(run)) {
      this.publish({ run: await this.api.cancel(run.id) });
      // The loop sees the run end; a run that does not end in time is reported, not hidden.
      const following = this.following;
      if (following) await Promise.race([following, pause(6000)]);
      if (this.view.run && !terminal(this.view.run)) throw new AgentApiFailure("AGENT_CLEANUP_FAILED");
    }
    this.pending = null; this.publish({ pendingSend: false, submitting: false });
  }
  close(): void { this.closed = true; ++this.epoch; ++this.sendEpoch; this.stream?.abort(); }
}
