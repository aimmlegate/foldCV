import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { WriterApi } from "../../src/background/api";
import type { WriterProofV1 } from "../../src/contracts/generated/background_writer_proof_v1";
import { decodeJsonResponse } from "../../src/contracts/json-response";
import { parseJsonWire, type JsonWireNode } from "../../src/contracts/lossless-json";
import { RichApiFailure } from "../../src/rich/api";

/** Isolated loopback Python writer over a synthetic temporary store; no provider or user data. */
export const root = new URL("../../../../", import.meta.url).pathname;
export type Harness = { origin: string; project: string; proof: WriterProofV1; close: () => Promise<void> };

export function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
export function string(value: unknown): string { assert.equal(typeof value, "string"); return String(value); }
export function number(value: unknown): number { assert.equal(typeof value, "number"); return Number(value); }

export async function harness(scenario = "joined"): Promise<Harness> {
  const directory = mkdtempSync(join(realpathSync(tmpdir()), "foldcv-v7-queue-"));
  const child = spawn(join(root, ".venv/bin/python"), [join(root, "tools/template_writer_harness.py"), directory, scenario],
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
    const handshake = record(JSON.parse(first)), proof = record(handshake["proof"]), origin = string(handshake["origin"]);
    assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/u, "loopback only");
    return { origin, project: string(handshake["project"]),
      proof: { schemaVersion: 1, lineage: string(proof["lineage"]), epoch: number(proof["epoch"]), sessionId: string(proof["sessionId"]),
        incarnation: string(proof["incarnation"]), credential: string(proof["credential"]) }, close: cleanup };
  } catch (error) { await cleanup(); throw error; }
}

export type Traffic = { path: string; wire: string; reply?: unknown };
/** A transport fault: by default the request is processed and its reply lost; `before` drops it unsent;
 * `replace` delivers another (for example older) reply instead of the real one. */
export type Fault = { path: string; times: number; before?: boolean; replace?: unknown };
export const meter = { active: 0, peak: 0 };
export function client(value: Harness, traffic: Traffic[], fault: Fault | null = null) {
  async function send(path: string, init: RequestInit, wire: string): Promise<unknown> {
    const entry: Traffic = { path, wire };
    traffic.push(entry);
    if (fault?.before && path.endsWith(fault.path) && fault.times > 0) { fault.times--; throw new TypeError("fetch failed"); }
    meter.active++; meter.peak = Math.max(meter.peak, meter.active);
    const response = await fetch(value.origin + "/v1/rich/projects" + path, init).finally(() => { meter.active--; });
    const decoded = decodeJsonResponse(await response.text());
    if (!response.ok) {
      const error = record(record(decoded)["error"]);
      throw new RichApiFailure(string(error["code"]), response.status);
    }
    entry.reply = decoded;
    // A processed request whose reply is lost exercises identical retry of frozen bytes.
    if (fault && !fault.before && path.endsWith(fault.path) && fault.times > 0) {
      fault.times--;
      if (fault.replace !== undefined) return fault.replace;
      throw new TypeError("fetch failed");
    }
    return decoded;
  }
  const json = (path: string, method = "GET", body?: unknown) => {
    const wire = body === undefined ? "" : JSON.stringify(body);
    return send(path, { method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: wire }) }, wire);
  };
  const raw = (path: string, body: JsonWireNode) => send(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body.wire }, body.wire);
  return new WriterApi(value.project, json, raw);
}

export async function bootstrap(value: Harness): Promise<JsonWireNode> {
  const response = await fetch(`${value.origin}/v1/rich/projects/${value.project}/writer/read`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(value.proof) });
  assert.equal(response.status, 200);
  return parseJsonWire(await response.text());
}
