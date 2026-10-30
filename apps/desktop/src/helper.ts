import { spawn } from "node:child_process";
import { createWriteStream, mkdirSync, renameSync, statSync } from "node:fs";
import { dirname } from "node:path";
import { finished } from "node:stream/promises";
import type { HelperCommand } from "./platform.js";

/** Where the page is served and the one-time secret that opens its session. */
export type Endpoint = { origin: string; secret: string };
export type Helper = { endpoint: Endpoint; exited: Promise<number | null>; stop(): Promise<void> };

const ORIGIN = /^http:\/\/127\.0\.0\.1:\d{1,5}$/u;
const LOG_BYTES = 5 * 1024 * 1024;

export function readyLine(line: string): Endpoint {
  const value: unknown = JSON.parse(line);
  const origin: unknown = typeof value === "object" && value !== null ? Reflect.get(value, "origin") : null;
  const secret: unknown = typeof value === "object" && value !== null ? Reflect.get(value, "secret") : null;
  if (typeof origin !== "string" || !ORIGIN.test(origin) || typeof secret !== "string" || secret.length < 32) {
    throw new Error("HELPER_PROTOCOL");
  }
  return { origin, secret };
}

function within(promise: Promise<unknown>, milliseconds: number): Promise<boolean> {
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(false), milliseconds);
    void promise.then(() => { clearTimeout(timer); resolve(true); });
  });
}

function openLog(path: string): NodeJS.WritableStream {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  try { if (statSync(path).size > LOG_BYTES) renameSync(path, path + ".1"); } catch { /* No log yet. */ }
  return createWriteStream(path, { flags: "a", mode: 0o600 });
}

/** Start the helper's `serve <root>` command; resolves when the service reports its endpoint. Its stderr goes to
 * `log`. */
export function startHelper(command: HelperCommand, environment: Record<string, string>, log: string,
  timeout = 120_000): Promise<Helper> {
  // No console window on Windows; the service's own workers start without one too.
  const child = spawn(command.executable, command.args, { stdio: ["pipe", "pipe", "pipe"], env: environment,
    windowsHide: true });
  const output = openLog(log);
  child.stderr.pipe(output);
  child.stdin.on("error", () => { /* The helper may be gone already; `exited` reports it. */ });
  // Settles once the process is gone and its last log lines are written.
  const exited = Promise.all([new Promise<number | null>(resolve => { child.once("close", code => resolve(code)); }),
    finished(output).catch(() => undefined)]).then(([code]) => code);
  async function stop(): Promise<void> {
    if (child.exitCode !== null || child.signalCode !== null) return;
    // EOF on stdin asks for a graceful shutdown; signals only follow when it does not come.
    child.stdin.end();
    if (await within(exited, 20_000)) return;
    child.kill("SIGTERM");
    if (await within(exited, 5_000)) return;
    child.kill("SIGKILL");
    await exited;
  }
  return new Promise((resolve, reject) => {
    let buffer = "", settled = false;
    const fail = (error: Error) => {
      if (settled) return;
      settled = true; clearTimeout(timer); child.kill("SIGKILL"); reject(error);
    };
    const timer = setTimeout(() => fail(new Error("HELPER_TIMEOUT")), timeout);
    child.once("error", () => fail(new Error("HELPER_UNAVAILABLE")));
    void exited.then(() => fail(new Error("HELPER_EXITED")));
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      if (settled) return;
      buffer += chunk;
      const end = buffer.indexOf("\n");
      if (end < 0) { if (buffer.length > 4096) fail(new Error("HELPER_PROTOCOL")); return; }
      let endpoint: Endpoint;
      try { endpoint = readyLine(buffer.slice(0, end)); } catch { fail(new Error("HELPER_PROTOCOL")); return; }
      settled = true; clearTimeout(timer);
      resolve({ endpoint, exited, stop });
    });
  });
}
