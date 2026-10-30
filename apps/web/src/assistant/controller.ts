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
/** The loading line of a run whose follow loop gave up; Stop follows the run again. */
export const lostLink = "Нет связи с помощником";
export const terminal = (run: Run | null): boolean => run !== null && ["completed", "failed", "cancelled", "interrupted"].includes(run.state);
export type AssistantView = {
  settings: AgentSettings | null; capabilities: AssistantCapabilitiesV1 | null; flags: AgentFlags;
  conversations: AssistantConversationV1[]; conversationId: string | null; messages: AssistantMessage[];
  sources: AssistantSource[]; findings: AssistantFinding[]; files: AssistantFileV1[]; run: Run | null;
  activity: AssistantEvent[]; partial: string; partialTruncated: boolean;
  proposals: Proposal[]; proposalBusy: string | null; proposalAction: "apply" | "discard" | null; staleProposals: string[];
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
// A failed poll is retried after a doubling pause of at most 20 × the base (5 s, below Stop's 6 s wait): about two
// minutes at the default base before the panel reports the run as unreachable.
const FOLLOW_RETRIES = 30;
function code(error: unknown): string {
  return error instanceof AgentApiFailure ? error.code : error instanceof Error && /^[A-Z][A-Z0-9_]+$/u.test(error.message) ? error.message : "REQUEST_FAILED";
}
// A missing run or a refused request stays so; a network or service failure may pass.
const lasting = (error: unknown): boolean => error instanceof AgentApiFailure && error.status >= 400 && error.status < 500
  && ![408, 409, 429].includes(error.status);

export class AssistantController {
  view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: true }, conversations: [],
    conversationId: null, messages: [], sources: [], findings: [], files: [], run: null, activity: [], partial: "",
    partialTruncated: false, proposals: [], proposalBusy: null, proposalAction: null, staleProposals: [], draft: "", submitting: false,
    pendingSend: false, error: null };
  private closed = false;
  private epoch = 0;
  private sendEpoch = 0;
  private stream: AbortController | null = null;
  private following: Promise<void> | null = null;
  private pending: Pending | null = null;
  // Message reads answer out of order: `reads` numbers them, `applied` is the newest one shown.
  private reads = 0;
  private applied = 0;
  private readonly drafts = new Map<string, string>();
  // The whole conversation as last read; the transcript shows sources and findings as they arrive or are opened.
  private loaded: { sources: AssistantSource[]; findings: AssistantFinding[] } = { sources: [], findings: [] };

  constructor(readonly api: Port, private readonly editor: AssistantEditor, private readonly changed: (view: AssistantView) => void,
    private readonly retryMs = 250, private readonly stopMs = 6000) {}

  get active(): boolean { return this.view.submitting || this.view.pendingSend || this.view.proposalBusy !== null || this.view.run !== null && !terminal(this.view.run); }
  private publish(update: Partial<AssistantView>): void {
    if (this.closed) return;
    this.view = { ...this.view, ...update }; this.changed(this.view);
  }
  private readonly waiting = new Map<symbol, string>();
  // The follow loop's line in the loading state: reconnecting, or lost until the run is followed again.
  private readonly link = Symbol();
  private label(key: symbol, text: string | null): void {
    if (text === null) this.waiting.delete(key); else this.waiting.set(key, text);
    this.publish({ loading: [...this.waiting.values()].at(-1) ?? null });
  }
  private async wait<T>(label: string, work: () => Promise<T>): Promise<T> {
    const key = Symbol(); this.label(key, label);
    try { return await work(); }
    finally { this.label(key, null); }
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
  async refresh(): Promise<void> { return this.wait("Обновляем", () => this.refreshWork()); }
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
    return this.wait("Сохраняем модель", async () => {
      const settings = this.view.settings;
      if (!settings) return;
      const effort = settings.reasoningEffort ?? null;
      const save = (reasoningEffort: typeof effort) => this.api.saveSettings({ expectedRevision: settings.revision, enabled,
        selectedAgentModel: model, reasoningEffort });
      try {
        let next: AgentSettings, notice: string | null = null;
        try { next = await save(effort); }
        catch (error) {
          // The stored level goes only when the new model lacks it, and the panel says so.
          if (effort === null || code(error) !== "AGENT_MODEL_INCOMPATIBLE") throw error;
          next = await save(null); notice = "AGENT_REASONING_DROPPED";
        }
        this.publish({ settings: next, error: notice }); await this.refreshWork();
      } catch (error) { this.publish({ error: code(error) }); await this.refreshWork().catch(() => {}); }
    });
  }

  async newConversation(): Promise<void> {
    return this.wait("Создаём диалог", async () => {
      if (this.view.submitting || this.view.pendingSend || this.view.proposalBusy) throw new AgentApiFailure("AGENT_BUSY");
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
    if (this.view.submitting || this.view.pendingSend || this.view.proposalBusy) throw new AgentApiFailure("AGENT_BUSY");
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
  private leaveConversation(): number {
    this.stream?.abort(); this.stream = null; this.following = null; this.label(this.link, null);
    return ++this.epoch;
  }

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
    const id = this.view.conversationId, epoch = this.epoch, read = ++this.reads;
    if (!id) return;
    const value = await this.api.messages(id);
    if (this.closed || epoch !== this.epoch || read < this.applied) return;
    this.applied = read;
    this.loaded = { sources: value.sources, findings: value.findings };
    const runs = [...value.runs], shown = this.view.run, current = shown ? runs.find(run => run.id === shown.id) : undefined;
    // A read sent before the run ended can still say running; only a poll that follows the run moves its state on.
    const fresh = current && (!terminal(shown) || terminal(current));
    this.publish({ messages: messagesOf(value), files: [...value.files ?? []], ...(fresh ? { run: current } : {}) });
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

  /** One long-poll loop per run; it ends when the run ends, the conversation changes or the drawer closes. Failed
   * polls are retried with backoff while the panel shows the reconnect; past FOLLOW_RETRIES it reports the lost run. */
  private follow(run: Run): void {
    this.stream?.abort();
    const stream = new AbortController(), epoch = this.epoch;
    this.stream = stream;
    this.label(this.link, null);
    const work: Promise<void> = (async () => {
      let after = 0, failures = 0;
      while (!this.closed && !stream.signal.aborted && epoch === this.epoch) {
        try {
          const reply = await this.api.events(run.id, after, stream.signal);
          if (this.closed || stream.signal.aborted || epoch !== this.epoch) return;
          if (reply.run.id !== run.id || reply.events.some(event => event.runId !== run.id)) throw new AgentApiFailure("INVALID_RESULT");
          if (failures > 0) { failures = 0; this.label(this.link, null); }
          for (const event of reply.events) if (event.sequence > after) this.accept(event);
          after = Math.max(after, reply.next);
          this.publish({ run: reply.run });
          if (terminal(reply.run)) { await this.finishRun(); return; }
        } catch (error) {
          if (this.closed || stream.signal.aborted || epoch !== this.epoch) return;
          if (lasting(error)) { this.label(this.link, null); this.publish({ error: code(error) }); return; }
          if (++failures > FOLLOW_RETRIES) {
            this.label(this.link, lostLink);
            this.publish({ error: error instanceof AgentApiFailure ? error.code : "SERVICE_UNAVAILABLE" });
            return;
          }
          this.label(this.link, "Восстанавливаем связь с помощником");
          await pause(Math.min(this.retryMs * 2 ** (failures - 1), this.retryMs * 20));
        }
      }
    })().catch(error => { this.publish({ error: code(error) }); })
      .finally(() => { if (this.following === work) this.following = null; });
    this.following = work;
  }
  /** The run ended: its answer, files and proposals are read. */
  private async finishRun(): Promise<void> {
    await this.reloadMessages(); await this.refreshProposals();
    this.publish({ partial: "" });
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
    this.publish({ proposalBusy: proposal.id, proposalAction: "apply", error: null });
    try {
      const result = await this.editor.applyProposal(proposal.id, this.view.flags.allowEdits);
      this.publish({ proposals: this.view.proposals.map(item => item.id === result.proposal.id ? result.proposal : item) });
      if (result.action) await this.editor.actionApplied?.(result.action);
    } catch (error) {
      const failure = code(error);
      if (failure === "ASSISTANT_PROPOSAL_STALE") this.publish({ staleProposals: [...new Set([...this.view.staleProposals, proposal.id])] });
      this.publish({ error: failure });
    } finally {
      this.publish({ proposalBusy: null, proposalAction: null });
      await this.refreshProposals().catch(() => {});
    }
  }
  async discardProposal(proposal: Proposal): Promise<void> {
    if (this.closed || this.view.proposalBusy || proposal.state !== "draft") return;
    this.publish({ proposalBusy: proposal.id, proposalAction: "discard", error: null });
    try {
      const value = await this.api.discard(proposal.id);
      this.publish({ proposals: this.view.proposals.map(item => item.id === value.id ? value : item) });
    } catch (error) { this.publish({ error: code(error) }); }
    finally { this.publish({ proposalBusy: null, proposalAction: null }); }
  }

  async stop(): Promise<void> { return this.wait("Останавливаем", () => this.stopWork()); }
  private async stopWork(): Promise<void> {
    ++this.sendEpoch;
    await this.repeatPending();
    const run = this.view.run;
    if (run && !terminal(run)) {
      const reply = await this.api.cancel(run.id);
      this.publish({ run: reply }); this.label(this.link, null);
      if (!this.following) {
        this.publish({ error: null });
        // A loop that lost the run follows it again from the start, so the partial answer is read again too.
        if (terminal(reply)) await this.finishRun();
        else { this.publish({ partial: "", partialTruncated: false, activity: [] }); this.follow(run); }
      }
      // The loop sees the run end. A run that does not end in time is reported until it does; the loop still follows it.
      const following = this.following;
      if (following) await Promise.race([following, pause(this.stopMs)]);
      if (this.view.run && !terminal(this.view.run)) throw new AgentApiFailure("AGENT_STOP_PENDING");
    }
    this.pending = null; this.publish({ pendingSend: false, submitting: false });
  }
  /** Stop on a lost send reply: the same request returns the run the server may have started, so it can be cancelled.
   * A refusal means no run started; any other failure leaves the send pending and is reported. */
  private async repeatPending(): Promise<void> {
    const pending = this.pending;
    if (!pending || !this.view.pendingSend || this.view.submitting) return;
    try {
      const run = await this.api.submit(pending.conversationId, pending.request);
      this.pending = null;
      this.publish({ run, draft: "", partial: "", partialTruncated: false, activity: [], pendingSend: false, error: null });
      await this.reloadMessages().catch(() => {});
    } catch (error) {
      if (!(error instanceof AgentApiFailure && error.status >= 400 && error.status < 500)) throw error;
      this.pending = null;
      this.publish({ pendingSend: false, error: code(error) });
    }
  }
  close(): void { this.closed = true; ++this.epoch; ++this.sendEpoch; this.stream?.abort(); }
}
