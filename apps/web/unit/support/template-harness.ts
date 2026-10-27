import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { ProjectEditorConnection, type Fetcher } from "../../src/rich/v7-connection";

/** Isolated loopback Python service with the /v2 project routes over a synthetic temporary store; no provider or user data. */
export const root = new URL("../../../../", import.meta.url).pathname;
export type Harness = { origin: string; project: string; close: () => Promise<void> };

export function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
export function string(value: unknown): string { assert.equal(typeof value, "string"); return String(value); }

export async function harness(scenario = "joined"): Promise<Harness> {
  const directory = mkdtempSync(join(realpathSync(tmpdir()), "foldcv-v7-queue-"));
  const child = spawn(join(root, ".venv/bin/python"), [join(root, "apps/web/unit/support/template_harness.py"), directory, scenario],
    { cwd: root, stdio: ["pipe", "pipe", "inherit"] });
  const exited = new Promise<void>(resolve => child.once("exit", () => resolve()));
  const cleanup = async () => {
    child.stdin.end();
    // Bounded shutdown: a harness that ignores stdin closure is killed, then its synthetic store is removed.
    const timer = setTimeout(() => child.kill("SIGKILL"), 10_000);
    await exited; clearTimeout(timer);
    rmSync(directory, { recursive: true, force: true });
  };
  const lines = createInterface({ input: child.stdout });
  try {
    const first = await new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("harness startup timed out")), 60_000);
      lines.once("line", line => { clearTimeout(timer); resolve(line); });
      child.once("exit", code => { clearTimeout(timer); reject(new Error(`harness exited ${String(code)}`)); });
    });
    // Only the project and the loopback origin are read; any other handshake field is ignored.
    const handshake = record(JSON.parse(first)), origin = string(handshake["origin"]);
    assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/u, "loopback only");
    return { origin, project: string(handshake["project"]), close: cleanup };
  } catch (error) { await cleanup(); throw error; }
}

export type Traffic = { path: string; wire: string; reply?: unknown };
/** A transport fault: by default the request is processed and its reply lost; `before` drops it unsent;
 * `replace` delivers another (for example older) reply instead of the real one. */
export type Fault = { path: string; times: number; before?: boolean; replace?: unknown };
export function projectFetcher(value: Harness, traffic: Traffic[] = [], fault: Fault | null = null): Fetcher {
  return async (path, init) => {
    const entry: Traffic = { path, wire: typeof init.body === "string" ? init.body : "" };
    traffic.push(entry);
    if (fault?.before && path.endsWith(fault.path) && fault.times > 0) { fault.times--; throw new TypeError("fetch failed"); }
    const response = await fetch(value.origin + path, init);
    entry.reply = JSON.parse(await response.clone().text()) as unknown;
    if (fault && !fault.before && path.endsWith(fault.path) && fault.times > 0) {
      fault.times--;
      if (fault.replace !== undefined) return new Response(JSON.stringify(fault.replace), { status: 200 });
      throw new TypeError("fetch failed");
    }
    return response;
  };
}
export function projectClient(value: Harness, traffic: Traffic[] = [], fault: Fault | null = null): Promise<ProjectEditorConnection> {
  return ProjectEditorConnection.open(value.project, projectFetcher(value, traffic, fault));
}
