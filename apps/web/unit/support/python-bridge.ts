import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { RichApiFailure } from "../../src/rich/api";
import { WriterApi, JobsApi, type BackgroundRequest } from "../../src/background/api";
import { deferred } from "./background-writer";

const repository = fileURLToPath(new URL("../../../../", import.meta.url));
function record(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
type Ready = { project: string; conversation: string; root: string; synthetic: true; capacity: 1 };

export class PythonBridge {
  private readonly child: ChildProcessWithoutNullStreams;
  private readonly ready = deferred<Ready>();
  private readonly exited = deferred<{ code: number | null; signal: NodeJS.Signals | null }>();
  private readonly pending = new Map<number, ReturnType<typeof deferred<unknown>>>();
  private readonly hooks = new Map<string, ReturnType<typeof deferred<Record<string, unknown>>>>();
  private sequence = 0;
  private stderr = "";
  private closing = false;
  private constructor(readonly root: string) {
    const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(?:OPENAI_|CODEX_|T3CODE_|ANTHROPIC_|GEMINI_|AZURE_OPENAI_|MISTRAL_)/u.test(key)));
    this.child = spawn(join(repository, ".venv/bin/python"), ["-m", "spikes.background.writer_bridge", root],
      { cwd: repository, env, stdio: ["pipe", "pipe", "pipe"] });
    createInterface({ input: this.child.stdout }).on("line", (line: string) => {
      try { this.accept(JSON.parse(line) as unknown); }
      catch (error) { this.ready.reject(error); for (const pending of this.pending.values()) pending.reject(error); }
    });
    this.child.stderr.on("data", (chunk: Buffer) => { this.stderr = (this.stderr + chunk.toString()).slice(-16384); });
    this.child.on("error", error => { this.ready.reject(error); for (const pending of this.pending.values()) pending.reject(error); });
    this.child.on("close", (code, signal) => {
      this.exited.resolve({ code, signal });
      const failure = new Error(`Python bridge exited ${String(code)} ${String(signal)}: ${this.stderr}`);
      this.ready.reject(failure); for (const pending of this.pending.values()) pending.reject(failure);
      for (const hook of this.hooks.values()) hook.reject(failure);
    });
  }
  static async start(): Promise<{ bridge: PythonBridge; ready: Ready }> {
    const root = await mkdtemp(join(await realpath(tmpdir()), "foldcv-nb03-bridge-")), bridge = new PythonBridge(root);
    try { const ready = await bridge.ready.promise; return { bridge, ready }; }
    catch (error) { bridge.child.stdin.end(); await bridge.exited.promise; await rm(root, { recursive: true }); throw error; }
  }
  private accept(value: unknown): void {
    if (!record(value)) throw new Error("Invalid Python bridge frame");
    if (value.event === "ready") {
      if (typeof value.project !== "string" || typeof value.conversation !== "string" || value.root !== this.root
        || value.synthetic !== true || value.capacity !== 1) throw new Error("Unsafe Python bridge identity");
      this.ready.resolve({ project: value.project, conversation: value.conversation, root: this.root, synthetic: true, capacity: 1 });
    } else if (value.event === "hook") {
      if (typeof value.token !== "string") throw new Error("Invalid bridge hook");
      this.hooks.get(value.token)?.resolve(value);
    } else {
      if (typeof value.id !== "number") throw new Error("Missing bridge reply identity");
      const pending = this.pending.get(value.id); if (!pending) throw new Error("Unknown bridge reply");
      this.pending.delete(value.id);
      if (record(value.error)) pending.reject(new Error(`${String(value.error.type)}: ${String(value.error.message)}`));
      else pending.resolve(value.result);
    }
  }
  call(body: Record<string, unknown>): Promise<unknown> {
    const id = ++this.sequence, pending = deferred<unknown>(); this.pending.set(id, pending);
    this.child.stdin.write(JSON.stringify({ ...body, id }) + "\n"); return pending.promise;
  }
  async hold(name: string, family: "writer" | "job" | "http" = "writer", options: { jobOnly?: boolean } = {}) {
    const token = crypto.randomUUID(), reached = deferred<Record<string, unknown>>(); this.hooks.set(token, reached);
    void reached.promise.catch(() => {});
    await this.call({ kind: "hold", name, family, token, ...options });
    let released = false;
    return { reached: reached.promise, release: async () => {
      if (released) return; released = true;
      await this.call({ kind: "release", token }); this.hooks.delete(token);
    } };
  }
  readonly transport: BackgroundRequest = async (path, method = "GET", body) => {
    return this.http(`/v1/rich/projects${path}`, method, body);
  };
  async http(path: string, method = "GET", body?: unknown): Promise<unknown> {
    const result = await this.call({ kind: "http", path, method, ...(body === undefined ? {} : { body }) });
    if (!record(result) || typeof result.status !== "number") throw new Error("Invalid bridge HTTP result");
    if (result.status >= 400) throw new RichApiFailure(record(result.value) && record(result.value.error)
      && typeof result.value.error.code === "string" ? result.value.error.code : "REQUEST_FAILED", result.status);
    return result.value;
  }
  writer(project: string): WriterApi { return new WriterApi(project, this.transport); }
  jobs(project: string): JobsApi { return new JobsApi(project, this.transport); }
  async close(retain = false): Promise<void> {
    if (this.closing) return; this.closing = true;
    try { await this.call({ kind: "close" }); }
    finally { this.child.stdin.end(); }
    const ended = await this.exited.promise;
    if (ended.code !== 0 || ended.signal !== null) throw new Error(`Unclean Python bridge shutdown: ${this.stderr}`);
    if (this.pending.size) throw new Error("Python bridge left pending requests");
    if (retain) process.stderr.write(`Retained synthetic Python bridge: ${this.root}\n`);
    else await rm(this.root, { recursive: true });
  }
}
