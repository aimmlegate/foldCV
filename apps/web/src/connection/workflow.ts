import { validReasoning, type ModelReasoning } from "./reasoning";
import type { CliInstallationPayload } from "../contracts/generated/cli_installation_payload";

export type ConnectionState = "unchecked" | "detached" | "cli_missing" | "launcher_unsupported" | "unsupported_version" |
  "login_required" | "api_key_mode" | "metadata_failed" | "quota_exhausted" |
  "unknown_limits" | "connected" | "login_pending" | "login_failed" | "cleanup_blocked";

export type CliInstallation = CliInstallationPayload;
export type ProviderKind = "codex_cli" | "claude_cli";
export type QuotaState = "unknown" | "available" | "exhausted" | "not_provided";
export type Quota = { state: QuotaState; usedPercent: number | null; resetsAt: number | null };

/** One provider with its own connection (D119: every provider that is on stays connected at the same time). */
export type ProviderEntry = {
  kind: ProviderKind; display: string; subscription: string; publisher: string; loginCode: boolean; installed: boolean;
  enabled: boolean; state: ConnectionState; version: string | null; versionStatus: "supported" | "graceful" | null;
  plan: string | null; models: string[]; modelReasoning?: Record<string, ModelReasoning>; quota: Quota;
  metadataReady: boolean; installation?: CliInstallation | null;
};

export type ConnectionSnapshot = {
  // The provider the reply named, with its state at the top level; null only before the first server reply.
  provider: ProviderKind | null;
  providers: ProviderEntry[];
  state: ConnectionState;
  version: string | null;
  versionStatus: "supported" | "graceful" | null;
  plan: string | null;
  quota: Quota;
  installation?: CliInstallation | null;
  // The catalog of every provider that is on; `selectedModel` is the processing model.
  models: string[];
  selectedModel: string | null;
  modelReasoning?: Record<string, ModelReasoning>;
  metadataReady: boolean;
  generationReady: boolean;
  experimentalMode: boolean;
};

export type ProviderActivity = { pending: boolean; detaching: boolean; error: string | null };
export type ConnectionView = { snapshot: ConnectionSnapshot; pending: boolean; detaching: boolean; error: string | null;
  activity: Partial<Record<ProviderKind, ProviderActivity>> };

const states = new Set<ConnectionState>(["unchecked", "detached", "cli_missing", "launcher_unsupported", "unsupported_version", "login_required",
  "api_key_mode", "metadata_failed", "quota_exhausted", "unknown_limits", "connected", "login_pending",
  "login_failed", "cleanup_blocked"]);
const model = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$/;
const kinds: readonly string[] = ["codex_cli", "claude_cli"];
const installingStates: readonly string[] = ["downloading", "verifying", "extracting"];
const initial: ConnectionSnapshot = { provider: null, providers: [], state: "unchecked", version: null,
  versionStatus: null, plan: null, models: [], selectedModel: null,
  quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false,
  generationReady: false, experimentalMode: false };

export type ModelGroup = { label: string; models: string[] };

/** The offered models grouped by the provider that runs them, in the server's order. */
export function modelGroups(snapshot: ConnectionSnapshot | null): ModelGroup[] {
  if (!snapshot) return [];
  return snapshot.providers.filter(entry => entry.enabled)
    .map(entry => ({ label: entry.display, models: snapshot.models.filter(name => entry.models.includes(name)) }))
    .filter(group => group.models.length > 0);
}

/** The provider that runs a model, while it is on and lists the model. */
export function modelProvider(snapshot: ConnectionSnapshot, name: string): ProviderEntry | undefined {
  return snapshot.providers.find(entry => entry.enabled && entry.models.includes(name));
}

/** The sidebar line: the providers connected now, else whether a check is still due. */
export function connectionSummary(snapshot: ConnectionSnapshot | null): string {
  const on = snapshot?.providers.filter(entry => entry.enabled) ?? [];
  const connected = on.filter(entry => entry.state === "connected").map(entry => entry.display);
  if (connected.length) return `${connected.join(" и ")} · подписка`;
  return !snapshot || on.some(entry => entry.state === "unchecked") ? "Подключение не проверено" : "Модель отключена";
}

export const loginCodePattern = /^[A-Za-z0-9._~#-]{1,512}$/;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validInstallation(value: unknown): value is CliInstallation {
  const errors: readonly string[] = ["unsafe_directory", "busy", "cancelled", "unsupported_platform", "download_failed",
    "invalid_package", "checksum_failed", "install_failed"];
  return record(value) && typeof value.state === "string" && ["idle", "downloading", "verifying", "extracting", "ready", "failed", "cancelled"].includes(value.state) &&
    typeof value.downloadedBytes === "number" && Number.isSafeInteger(value.downloadedBytes) && value.downloadedBytes >= 0 &&
    typeof value.totalBytes === "number" && Number.isSafeInteger(value.totalBytes) && value.totalBytes > 0 &&
    value.downloadedBytes <= value.totalBytes && typeof value.available === "boolean" &&
    typeof value.version === "string" && /^[0-9a-zA-Z.-]{1,60}$/.test(value.version) &&
    (value.error === null || typeof value.error === "string" && errors.includes(value.error));
}

function validQuota(quota: unknown): boolean {
  return record(quota) && ["unknown", "available", "exhausted", "not_provided"].includes(String(quota.state)) &&
    (quota.usedPercent === null || (typeof quota.usedPercent === "number" && Number.isFinite(quota.usedPercent) && quota.usedPercent >= 0 && quota.usedPercent <= 100)) &&
    (quota.resetsAt === null || (typeof quota.resetsAt === "number" && Number.isSafeInteger(quota.resetsAt) && quota.resetsAt >= 0));
}

function validModels(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 100 && value.every((entry: unknown) => typeof entry === "string" && model.test(entry)) &&
    new Set(value).size === value.length;
}

/** The state fields a provider entry and the top level share. */
function validState(value: Record<string, unknown>): boolean {
  return typeof value.state === "string" && states.has(value.state as ConnectionState) &&
    (value.versionStatus === null || value.versionStatus === "supported" || value.versionStatus === "graceful") &&
    (value.version === null || (typeof value.version === "string" && value.version.length <= 80)) &&
    (value.plan === null || (typeof value.plan === "string" && /^[a-z][a-z0-9_]{0,39}$/.test(value.plan))) &&
    validQuota(value.quota) && (value.installation === undefined || value.installation === null || validInstallation(value.installation));
}

function validProvider(item: unknown): item is ProviderEntry {
  const name = (entry: unknown) => typeof entry === "string" && entry.length > 0 && entry.length <= 40;
  return record(item) && kinds.includes(String(item.kind)) && name(item.display) && name(item.subscription) && name(item.publisher) &&
    typeof item.loginCode === "boolean" && typeof item.installed === "boolean" && typeof item.enabled === "boolean" &&
    validState(item) && validModels(item.models) && typeof item.metadataReady === "boolean" &&
    (item.modelReasoning === undefined || validReasoning(item.modelReasoning, item.models));
}

export function validConnection(value: unknown): value is ConnectionSnapshot {
  if (!record(value) || typeof value.provider !== "string" || !kinds.includes(value.provider) || !validState(value) ||
      !Array.isArray(value.providers) || value.providers.length > 8 || !value.providers.every(validProvider) ||
      new Set(value.providers.map(item => item.kind)).size !== value.providers.length ||
      !value.providers.some(item => item.kind === value.provider) || !validModels(value.models) ||
      !value.models.every(name => (value.providers as ProviderEntry[]).some(item => item.enabled && item.models.includes(name))) ||
      !(value.selectedModel === null || (typeof value.selectedModel === "string" && value.models.includes(value.selectedModel))) ||
      typeof value.metadataReady !== "boolean" || typeof value.generationReady !== "boolean" ||
      typeof value.experimentalMode !== "boolean") return false;
  if (value.modelReasoning !== undefined && !validReasoning(value.modelReasoning, value.models)) return false;
  return !value.generationReady || (value.experimentalMode && value.selectedModel !== null);
}

export class ConnectionWorkflow {
  private epochs = new Map<ProviderKind, number>();
  private aborts = new Map<ProviderKind, AbortController>();
  private peeks = 0;
  private closed = false;
  private installationPoll: ReturnType<typeof setInterval> | null = null;
  private pollingInstallation = false;
  view: ConnectionView = { snapshot: initial, pending: false, detaching: false, error: null, activity: {} };

  constructor(private readonly onChange: (view: ConnectionView) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  private publish(snapshot: ConnectionSnapshot, activity: ConnectionView["activity"]): void {
    if (this.closed) return;
    const all = Object.values(activity);
    this.view = { snapshot, activity, pending: all.some(item => item?.pending), detaching: all.some(item => item?.detaching),
      error: all.find(item => item?.error)?.error ?? null };
    this.onChange(this.view);
    const installing = snapshot.providers.some(item => item.installation && installingStates.includes(item.installation.state));
    if (installing && !this.view.detaching && this.installationPoll === null) {
      this.installationPoll = setInterval(() => { void this.pollInstallation(); }, 300);
    } else if ((!installing || this.view.detaching) && this.installationPoll !== null) {
      clearInterval(this.installationPoll);
      this.installationPoll = null;
    }
  }

  /** Sets one provider's activity; `null` clears it. */
  private update(kind: ProviderKind, activity: ProviderActivity | null, snapshot: ConnectionSnapshot = this.view.snapshot): void {
    const next = { ...this.view.activity };
    if (activity) next[kind] = activity; else delete next[kind];
    this.publish(snapshot, next);
  }

  private activityOf(kind: ProviderKind): ProviderActivity {
    return this.view.activity[kind] ?? { pending: false, detaching: false, error: null };
  }

  entry(kind: ProviderKind): ProviderEntry | undefined {
    return this.view.snapshot.providers.find(item => item.kind === kind);
  }

  private begin(kind: ProviderKind): number {
    const epoch = (this.epochs.get(kind) ?? 0) + 1;
    this.epochs.set(kind, epoch);
    this.aborts.get(kind)?.abort();
    this.aborts.delete(kind);
    return epoch;
  }

  private current(kind: ProviderKind, epoch: number): boolean {
    return !this.closed && this.epochs.get(kind) === epoch;
  }

  private async pollInstallation(): Promise<void> {
    if (this.pollingInstallation || this.view.detaching) return;
    this.pollingInstallation = true;
    try {
      const snapshot = await this.post("peek", {}, null);
      const before = this.view.snapshot.providers;
      // A provider still waiting for its install reply keeps its activity; only the progress is taken.
      const providers = before.map(item => {
        const fresh = snapshot.providers.find(value => value.kind === item.kind);
        return fresh && this.activityOf(item.kind).pending ? { ...item, installation: fresh.installation ?? null } : fresh ?? item;
      });
      this.publish({ ...snapshot, providers }, this.view.activity);
      // An install that finished while Settings was away is followed by the check it would have run.
      for (const item of providers) {
        const was = before.find(value => value.kind === item.kind)?.installation?.state;
        if (was && installingStates.includes(was) && item.installation?.state === "ready" && item.state !== "detached"
            && !this.activityOf(item.kind).pending) await this.refresh(item.kind);
      }
    } catch { /* Keep the last observed progress until the next poll. */ }
    finally { this.pollingInstallation = false; }
  }

  private async post(path: string, body: object, kind: ProviderKind | null, signal?: AbortSignal): Promise<ConnectionSnapshot> {
    const peek = path === "peek";
    // Every host request names its provider, so a stale screen cannot act on another provider.
    const payload = kind === null ? body : { provider: kind, ...body };
    const response = await this.request(peek ? "/v1/settings/connection" : `/v1/host/${path}`, { method: peek ? "GET" : "POST", credentials: "same-origin",
      ...(peek ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }), ...(signal ? { signal } : {}) });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("request failed");
    const length = Number(response.headers.get("content-length") ?? "0");
    if (!Number.isFinite(length) || length > 65_536) throw new Error("response too large");
    if (!response.body) throw new Error("empty response");
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 65_536) throw new Error("response too large");
        chunks.push(value);
      }
    } catch (error) { await reader.cancel(); throw error; }
    finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    const value: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!validConnection(value)) throw new Error("invalid connection response");
    return value;
  }

  private async run(kind: ProviderKind, path: string, body: object = {}, failure = "Connection check failed. Try again."): Promise<void> {
    if (this.activityOf(kind).detaching) return;
    const epoch = this.begin(kind);
    const abort = new AbortController();
    this.aborts.set(kind, abort);
    this.update(kind, { pending: true, detaching: false, error: null }, { ...this.view.snapshot, generationReady: false });
    try {
      const snapshot = await this.post(path, body, kind, abort.signal);
      if (this.current(kind, epoch)) this.update(kind, null, snapshot);
    } catch {
      if (this.current(kind, epoch)) this.update(kind, { pending: false, detaching: false, error: failure });
    } finally { if (this.aborts.get(kind) === abort) this.aborts.delete(kind); }
  }

  /** Reads every provider without starting a process, then checks the providers that are on and not checked yet. */
  async peek(check = true): Promise<void> {
    const epoch = ++this.peeks;
    try {
      const snapshot = await this.post("peek", {}, null);
      if (this.closed || epoch !== this.peeks) return;
      this.publish(snapshot, this.view.activity);
    } catch {
      if (!this.closed && epoch === this.peeks) this.publish(this.view.snapshot, { ...this.view.activity });
      return;
    }
    if (check) await this.checkUnchecked();
  }

  async checkUnchecked(): Promise<void> {
    for (const item of this.view.snapshot.providers) {
      if (this.closed) return;
      const fresh = this.entry(item.kind);
      if (fresh?.enabled && fresh.state === "unchecked" && !this.activityOf(item.kind).pending) await this.refresh(item.kind);
    }
  }

  refresh(kind: ProviderKind): Promise<void> { return this.run(kind, "status"); }
  discover(kind: ProviderKind): Promise<void> { return this.run(kind, "discover"); }
  /** The processing model, saved through the provider that runs it. */
  select(modelName: string): Promise<void> {
    const owner = modelProvider(this.view.snapshot, modelName);
    if (!owner || !this.view.snapshot.models.includes(modelName)) return Promise.resolve();
    return this.run(owner.kind, "select", { model: modelName });
  }
  /** Turns a provider on (then checks it) or off (a clean detach on the server, never a sign-out). */
  async enable(kind: ProviderKind, enabled: boolean): Promise<void> {
    const item = this.entry(kind);
    if (!item || item.enabled === enabled || this.activityOf(kind).pending) return;
    const epoch = (this.epochs.get(kind) ?? 0) + 1;
    await this.run(kind, "enable", { enabled }, "Could not change the provider. Try again.");
    if (enabled && this.epochs.get(kind) === epoch && !this.activityOf(kind).error && this.entry(kind)?.state === "unchecked") await this.refresh(kind);
  }
  async install(kind: ProviderKind): Promise<void> {
    const item = this.entry(kind), installation = item?.installation;
    if (!item || this.activityOf(kind).pending || !installation?.available || installingStates.includes(installation.state)
        || !["cli_missing", "launcher_unsupported", "unsupported_version"].includes(item.state)) return;
    const providers = this.view.snapshot.providers.map(value => value.kind === kind
      ? { ...value, installation: { ...installation, state: "downloading" as const, downloadedBytes: 0, error: null } } : value);
    this.publish({ ...this.view.snapshot, providers }, this.view.activity);
    const epoch = (this.epochs.get(kind) ?? 0) + 1;
    await this.run(kind, "install");
    if (this.epochs.get(kind) === epoch && !this.activityOf(kind).error && this.entry(kind)?.installation?.state === "ready") await this.refresh(kind);
  }
  async cancelInstall(kind: ProviderKind): Promise<void> {
    if (this.activityOf(kind).detaching) return;
    const epoch = this.begin(kind);
    this.update(kind, { pending: true, detaching: false, error: null });
    try {
      const snapshot = await this.post("cancel-install", {}, kind);
      if (this.current(kind, epoch)) {
        this.update(kind, null, snapshot);
        const item = this.entry(kind);
        if (item?.installation?.state === "ready" && item.state !== "detached") await this.refresh(kind);
      }
    } catch { if (this.current(kind, epoch)) this.update(kind, { pending: false, detaching: false, error: "Could not cancel installation. Try again." }); }
  }
  async login(kind: ProviderKind): Promise<void> {
    if (this.entry(kind)?.state !== "login_required") return;
    const providers = this.view.snapshot.providers.map(value => value.kind === kind ? { ...value, state: "login_pending" as const } : value);
    this.publish({ ...this.view.snapshot, providers }, this.view.activity);
    const epoch = (this.epochs.get(kind) ?? 0) + 1;
    await this.run(kind, "login");
    if (this.epochs.get(kind) === epoch && this.entry(kind)?.state === "login_required" && !this.activityOf(kind).error) await this.refresh(kind);
  }
  /** Passes the code from the provider's sign-in page to the running sign-in; the reply changes nothing on screen. */
  async sendLoginCode(kind: ProviderKind, code: string): Promise<boolean> {
    const value = code.trim();
    if (this.entry(kind)?.state !== "login_pending" || !loginCodePattern.test(value)) return false;
    try { await this.post("login-code", { code: value }, kind); return true; }
    catch { this.update(kind, { ...this.activityOf(kind), error: "Could not send the sign-in code. Try again." }); return false; }
  }
  async cancelLogin(kind: ProviderKind): Promise<void> {
    if (this.activityOf(kind).detaching) return;
    const epoch = this.begin(kind);
    this.update(kind, { pending: true, detaching: false, error: null });
    try {
      const snapshot = await this.post("cancel-login", {}, kind);
      if (this.current(kind, epoch)) this.update(kind, null, snapshot);
    } catch { if (this.current(kind, epoch)) this.update(kind, { pending: false, detaching: false, error: "Could not stop sign-in. Try again." }); }
  }
  async detach(kind: ProviderKind): Promise<void> {
    if (this.activityOf(kind).detaching) return;
    const epoch = this.begin(kind);
    // The provider stays listed while it detaches; only its metadata is dropped.
    const providers = this.view.snapshot.providers.map(value => value.kind === kind
      ? { ...value, state: "unchecked" as const, models: [], modelReasoning: {}, metadataReady: false } : value);
    const models = this.view.snapshot.models.filter(name => !this.entry(kind)?.models.includes(name));
    const cleared = { ...this.view.snapshot, providers, models,
      selectedModel: models.includes(this.view.snapshot.selectedModel ?? "") ? this.view.snapshot.selectedModel : null,
      generationReady: false };
    this.update(kind, { pending: true, detaching: true, error: null }, cleared);
    try {
      const snapshot = await this.post("detach", {}, kind);
      if (this.current(kind, epoch)) this.update(kind, null, snapshot);
    } catch { if (this.current(kind, epoch)) this.update(kind, { pending: false, detaching: false, error: "Could not confirm detach. Try again." }, cleared); }
  }
  close(): void {
    this.closed = true;
    for (const abort of this.aborts.values()) abort.abort();
    this.aborts.clear();
    if (this.installationPoll !== null) clearInterval(this.installationPoll);
    this.installationPoll = null;
  }
}
