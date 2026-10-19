import { validReasoning, type ModelReasoning } from "./reasoning";
import type { CliInstallationPayload } from "../contracts/generated/cli_installation_payload";

export type ConnectionState = "unchecked" | "detached" | "cli_missing" | "launcher_unsupported" | "unsupported_version" |
  "login_required" | "api_key_mode" | "metadata_failed" | "quota_exhausted" |
  "unknown_limits" | "connected" | "login_pending" | "login_failed" | "cleanup_blocked";

export type CliInstallation = CliInstallationPayload;

export type ConnectionSnapshot = {
  state: ConnectionState;
  version: string | null;
  plan: string | null;
  models: string[];
  selectedModel: string | null;
  modelReasoning?: Record<string, ModelReasoning>;
  quota: { state: "unknown" | "available" | "exhausted"; usedPercent: number | null; resetsAt: number | null };
  metadataReady: boolean;
  generationReady: boolean;
  experimentalMode: boolean;
  installation?: CliInstallation | null;
};

export type ConnectionView = { snapshot: ConnectionSnapshot; pending: boolean; detaching: boolean; error: string | null };

const states = new Set<ConnectionState>(["unchecked", "detached", "cli_missing", "launcher_unsupported", "unsupported_version", "login_required",
  "api_key_mode", "metadata_failed", "quota_exhausted", "unknown_limits", "connected", "login_pending",
  "login_failed", "cleanup_blocked"]);
const model = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$/;
const initial: ConnectionSnapshot = { state: "unchecked", version: null, plan: null, models: [], selectedModel: null,
  quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false,
  generationReady: false, experimentalMode: false };

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

export function validConnection(value: unknown): value is ConnectionSnapshot {
  if (!record(value) || typeof value.state !== "string" || !states.has(value.state as ConnectionState) ||
      !(value.version === null || (typeof value.version === "string" && value.version.length <= 80)) ||
      !(value.plan === null || (typeof value.plan === "string" && /^[a-z][a-z0-9_]{0,39}$/.test(value.plan))) ||
      !Array.isArray(value.models) || value.models.length > 100 ||
      !value.models.every((entry: unknown) => typeof entry === "string" && model.test(entry)) ||
      new Set(value.models).size !== value.models.length ||
      !(value.selectedModel === null || (typeof value.selectedModel === "string" && value.models.includes(value.selectedModel))) ||
      typeof value.metadataReady !== "boolean" || typeof value.generationReady !== "boolean" ||
      typeof value.experimentalMode !== "boolean" || !record(value.quota)) return false;
  if (value.modelReasoning !== undefined && !validReasoning(value.modelReasoning, value.models)) return false;
  if (value.installation !== undefined && value.installation !== null && !validInstallation(value.installation)) return false;
  if (value.generationReady && (!value.experimentalMode || value.state !== "connected" || !value.metadataReady ||
      value.selectedModel === null || value.quota.state !== "available")) return false;
  const quota = value.quota;
  return ["unknown", "available", "exhausted"].includes(String(quota.state)) &&
    (quota.usedPercent === null || (typeof quota.usedPercent === "number" && Number.isFinite(quota.usedPercent) && quota.usedPercent >= 0 && quota.usedPercent <= 100)) &&
    (quota.resetsAt === null || (typeof quota.resetsAt === "number" && Number.isSafeInteger(quota.resetsAt) && quota.resetsAt >= 0));
}

export class ConnectionWorkflow {
  private epoch = 0;
  private abort: AbortController | null = null;
  private installationPoll: ReturnType<typeof setInterval> | null = null;
  private pollingInstallation = false;
  view: ConnectionView = { snapshot: initial, pending: false, detaching: false, error: null };

  constructor(private readonly onChange: (view: ConnectionView) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  private publish(view: ConnectionView): void {
    this.view = view;
    this.onChange(view);
    const active = view.snapshot.installation && ["downloading", "verifying", "extracting"].includes(view.snapshot.installation.state);
    if (active && !view.detaching && this.installationPoll === null) {
      this.installationPoll = setInterval(() => { void this.pollInstallation(); }, 300);
    } else if ((!active || view.detaching) && this.installationPoll !== null) {
      clearInterval(this.installationPoll);
      this.installationPoll = null;
    }
  }

  private async pollInstallation(): Promise<void> {
    if (this.pollingInstallation || this.view.detaching) return;
    const epoch = this.epoch;
    this.pollingInstallation = true;
    try {
      const snapshot = await this.post("peek", {});
      if (epoch !== this.epoch || !snapshot.installation) return;
      if (this.view.pending) {
        this.publish({ ...this.view, snapshot: { ...this.view.snapshot, installation: snapshot.installation } });
      } else {
        this.publish({ snapshot, pending: false, detaching: false, error: null });
        if (snapshot.installation.state === "ready" && snapshot.state !== "detached") await this.refresh();
      }
    } catch { /* Keep the last observed progress until the next poll. */ }
    finally { this.pollingInstallation = false; }
  }

  private async post(path: string, body: object, signal?: AbortSignal): Promise<ConnectionSnapshot> {
    const peek = path === "peek";
    const response = await this.request(peek ? "/v1/settings/connection" : `/v1/host/${path}`, { method: peek ? "GET" : "POST", credentials: "same-origin",
      ...(peek ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), ...(signal ? { signal } : {}) });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("request failed");
    const length = Number(response.headers.get("content-length") ?? "0");
    if (!Number.isFinite(length) || length > 32_768) throw new Error("response too large");
    if (!response.body) throw new Error("empty response");
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 32_768) throw new Error("response too large");
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

  private async run(path: string, body: object = {}): Promise<void> {
    if (this.view.detaching) return;
    this.epoch += 1;
    this.abort?.abort();
    const epoch = this.epoch;
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ ...this.view, snapshot: { ...this.view.snapshot, generationReady: false },
      pending: true, error: null });
    try {
      const snapshot = await this.post(path, body, abort.signal);
      if (epoch !== this.epoch) return;
      this.publish({ snapshot, pending: false, detaching: false, error: null });
    } catch {
      if (epoch !== this.epoch) return;
      this.publish({ ...this.view, pending: false, error: "Connection check failed. Try again." });
    } finally { if (this.abort === abort) this.abort = null; }
  }

  refresh(): Promise<void> { return this.run("status"); }
  async peek(): Promise<void> {
    const epoch = this.epoch + 1;
    await this.run("peek");
    if (epoch === this.epoch && !this.view.error && this.view.snapshot.state === "unchecked") await this.refresh();
  }
  discover(): Promise<void> { return this.run("discover"); }
  select(modelName: string): Promise<void> {
    if (!this.view.snapshot.models.includes(modelName)) return Promise.resolve();
    return this.run("select", { model: modelName });
  }
  async install(): Promise<void> {
    const installation = this.view.snapshot.installation;
    if (this.view.pending || !installation?.available || ["downloading", "verifying", "extracting"].includes(installation.state)
        || !["cli_missing", "launcher_unsupported", "unsupported_version"].includes(this.view.snapshot.state)) return;
    this.publish({ ...this.view, snapshot: { ...this.view.snapshot, installation: { ...installation, state: "downloading", downloadedBytes: 0, error: null } } });
    const epoch = this.epoch + 1;
    await this.run("install");
    if (epoch === this.epoch && !this.view.error && this.view.snapshot.installation?.state === "ready") await this.refresh();
  }
  async cancelInstall(): Promise<void> {
    if (this.view.detaching) return;
    this.epoch += 1;
    const epoch = this.epoch;
    this.publish({ ...this.view, pending: true, error: null });
    try {
      const snapshot = await this.post("cancel-install", {});
      if (epoch === this.epoch) {
        this.publish({ snapshot, pending: false, detaching: false, error: null });
        if (snapshot.installation?.state === "ready" && snapshot.state !== "detached") await this.refresh();
      }
    } catch { if (epoch === this.epoch) this.publish({ ...this.view, pending: false, error: "Could not cancel installation. Try again." }); }
  }
  async login(): Promise<void> {
    if (this.view.snapshot.state !== "login_required") return;
    this.publish({ snapshot: { ...this.view.snapshot, state: "login_pending" }, pending: true, detaching: false, error: null });
    const epoch = this.epoch + 1;
    await this.run("login");
    if (epoch === this.epoch && this.view.snapshot.state === "login_required" && !this.view.error) await this.refresh();
  }
  async cancelLogin(): Promise<void> {
    if (this.view.detaching) return;
    this.epoch += 1;
    const epoch = this.epoch;
    this.abort?.abort();
    this.abort = null;
    this.publish({ ...this.view, pending: true, error: null });
    try {
      const snapshot = await this.post("cancel-login", {});
      if (epoch !== this.epoch) return;
      this.publish({ snapshot, pending: false, detaching: false, error: null });
    } catch { if (epoch === this.epoch) this.publish({ ...this.view, pending: false, error: "Could not stop sign-in. Try again." }); }
  }
  async detach(): Promise<void> {
    if (this.view.detaching) return;
    this.epoch += 1;
    const epoch = this.epoch;
    this.abort?.abort();
    this.abort = null;
    this.publish({ snapshot: initial, pending: true, detaching: true, error: null });
    try {
      const snapshot = await this.post("detach", {});
      if (epoch !== this.epoch) return;
      this.publish({ snapshot, pending: false, detaching: false, error: null });
    } catch { if (epoch === this.epoch) this.publish({ snapshot: initial, pending: false, detaching: false,
      error: "Could not confirm detach. Try again." }); }
  }
  close(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    if (this.installationPoll !== null) clearInterval(this.installationPoll);
    this.installationPoll = null;
  }
}
