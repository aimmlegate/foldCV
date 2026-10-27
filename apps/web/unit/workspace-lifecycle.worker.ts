import assert from "node:assert/strict";
import { mock } from "node:test";
import type { RichEditorHandle } from "../src/rich/Editor";

function deferred() {
  let resolve: () => void = () => {}, reject: (error: Error) => void = () => {};
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const effects: (() => void | (() => void))[] = [], cleanups: (() => void)[] = [], events: string[] = [];
const scenario = process.argv[2] ?? "", importing = scenario.startsWith("import-");
const stateWrites = new Map<number, unknown[]>();
let stateIndex = 0, importReads = 0;
let mounted = true, staleState = 0;
Object.defineProperty(globalThis, "location", { value: { search: "?project=A", href: "http://foldcv.test/?project=A", pathname: "/" } });
Object.defineProperty(globalThis, "history", { value: { replaceState: (_data: unknown, _unused: string, url: string) => events.push(`url:${url}`) } });
mock.module("react", { namedExports: {
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void)) => { effects.push(effect); const cleanup = effect(); if (cleanup) cleanups.push(cleanup); },
  useRef: (current: unknown) => ({ current }),
  useState: (value: unknown): [unknown, (next: unknown) => void] => {
    const index = stateIndex++, initial: unknown = typeof value === "function" ? Reflect.apply(value, null, []) : value;
    return [importing && index === 8 ? { id: "synthetic" } : importing && index === 9 ? true : initial,
      (next: unknown) => { if (!mounted) staleState++; stateWrites.set(index, [...stateWrites.get(index) ?? [], next]); }];
  },
} });
const file = (path: string) => new URL(path, import.meta.url).href;
mock.module(file("../src/errors/messages.ts"), { namedExports: { errorMessage: (error: unknown) => String(error) } });
mock.module(file("../src/rich/import-source.ts"), { namedExports: { hasInput: () => importing, importBody: () => ({}) } });
const pendingRequest = deferred();
let holdRequest = false;
let holdFamilyRead = false;
mock.module(file("../src/rich/api.ts"), { namedExports: {
  deleteProject: async (id: string) => { events.push(`delete:${id}`); if (holdRequest) await pendingRequest.promise; return {}; },
  download: async () => new Blob(),
  downloadTemplate: async () => ({ blob: new Blob() }),
  openedProject: async (path: string) => {
    events.push(`request:${path}`);
    if (holdFamilyRead) await pendingRequest.promise;
    if (path === "/T" || path === "/template-input" || path === "/archive" && scenario === "template-upload")
      return { kind: "template", response: { workspace: { projectId: "T", project: {} }, identity: null } };
    return { kind: "rich", response: { workspace: { projectId: path === "/A" ? "A" : "B", project: {}, preDraft: null } } };
  },
  listProjects: async () => { events.push("catalog"); return { entries: [] }; },
  templateImportStatus: async () => null,
  request: async (path: string) => { events.push(`request:${path}`); return {}; },
  RichApiFailure: class extends Error {},
  projectRequest: async (path: string) => {
    events.push(`request:${path}`);
    return { workspace: { projectId: path === "/A" || path === "/A/activate" ? "A" : "B", project: {}, preDraft: null } };
  },
} });
mock.module(file("../src/background/connection.ts"), { namedExports: { attachExclusiveWriter: async () => null,
  attachExclusiveTemplateWriter: async (id: string) => { events.push(`attach-template:${id}`); return null; } } });
mock.module(file("../src/background/fixed.ts"), { namedExports: { FixedOperations: class {} } });
// The running attempt carries the server deadline from the default Settings import time (60 minutes),
// fixed on the test clock when the import starts.
let importDeadline: string | null = null;
const importJob = () => ({ id: "synthetic-job", execution: scenario === "import-timeout" ? "running" : scenario.slice("import-".length),
  publication: scenario === "import-cancelled" ? "cancelled" : "none", error: null, templateOutcome: null,
  attempts: [{ activeDeadline: importDeadline ??= new Date(Date.now() + 60 * 60_000).toISOString() }],
  submission: { templateCommand: { kind: "start_new_import", capture: { policy: { cleanupSeconds: 5, finalizationSeconds: 158 } } } } });
mock.module(file("../src/background/api.ts"), { namedExports: {
  JobsApi: class { async read() { importReads++; return importJob(); } },
  startTemplateImport: async () => { throw new Error("unused"); },
} });
const importState = scenario === "import-timeout" ? "running" : scenario === "import-cancelled" ? "cancelled" : "failed";
mock.module(file("../src/projects/api.ts"), { namedExports: {
  startImport: async () => {
    if (!importing) throw new Error("unused");
    events.push("import:start");
    return { id: "task-1", state: importState, stage: "processing", detail: {}, error: importState === "failed" ? "PROCESS_FAILED" : null };
  },
  projectTasks: async () => { importReads++; return [{ id: "task-1", state: "running", stage: "processing", detail: {}, error: null }]; },
  resumeImport: async () => { throw new Error("unused"); },
  cancelImport: async () => { events.push("import:cancel"); },
  openFoldcv: async () => {
    if (scenario !== "template-upload") throw new Error("unused");
    events.push("request:/v2/projects/archive");
    return { workspace: { projectId: "T", project: {} }, identity: null };
  },
  deleteTemplateProject: async () => { throw new Error("unused"); },
  catalogFlag: async (id: string, archived: boolean) => { events.push(`v2-catalog:${id}:${archived}`); },
} });
mock.module(file("../src/workbench/import/notices.ts"), { namedExports: { warningLabel: (value: unknown) => value } });
const { useResumeWorkspace } = await import("../src/workbench/useResumeWorkspace");
const hook = useResumeWorkspace();
await new Promise<void>(resolve => setImmediate(resolve));
events.length = 0;
const gate = deferred();
const editor: RichEditorHandle = {
  background: true, sessionId: "session", navigate: () => gate.promise,
  resume: async () => { events.push("resume"); }, undo: () => {}, redo: () => {},
  flush: async () => { throw new Error("Unexpected flush"); },
};
hook.editor.current = editor;
function unmount() {
  for (const cleanup of cleanups.splice(0)) cleanup();
  mounted = false;
}
function remount() {
  mounted = true;
  for (const effect of effects) { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); }
}
const [action, wait] = scenario.split(":");
if (wait === "assistant") {
  editor.background = false;
  editor.navigate = async () => { events.push("navigate"); };
  hook.assistant.current = { stop: () => gate.promise };
}
function invoke(): Promise<unknown> {
  switch (action) {
    case "open": return hook.open("B");
    case "upload": return hook.upload(new File(["synthetic"], "project.foldcv"));
    case "fresh": return hook.fresh();
    case "remove": return hook.remove("A");
    case "archive": return hook.archive("A", true);
    case "lifecycle": return hook.projectLifecycle("A", "archive");
    default: throw new Error(`Unknown action ${action}`);
  }
}
if (importing) {
  let now = Date.now();
  mock.method(Date, "now", () => now);
  const schedule = globalThis.setTimeout;
  mock.method(globalThis, "setTimeout", (callback: () => void) => { now += 60_000; return schedule(callback, 0); });
  await hook.process();
  // One read per minute until the attempt deadline plus cleanup (5 s), publication (158 s) and a minute.
  assert.equal(importReads, scenario === "import-timeout" ? 64 : 0);
  const expected = scenario === "import-timeout" ? "PROCESS_TIMEOUT" : scenario === "import-cancelled" ? "CANCELLED" : "PROCESS_FAILED";
  assert.ok(stateWrites.get(10)?.some(value => String(value).includes(expected)), "terminal imports report an error without an optional server error");
  assert.equal(stateWrites.get(12)?.at(-1), false, "the busy state is released");
  assert.equal(await hook.action(async () => {}), true, "another action is admitted after failure");
  mock.restoreAll();
} else if (wait) {
  const pending = invoke();
  await Promise.resolve(); unmount();
  if (wait === "remount") { remount(); await new Promise<void>(resolve => setImmediate(resolve)); }
  events.length = 0;
  gate.resolve();
  assert.equal(await pending, action === "fresh" ? undefined : false);
  assert.deepEqual(events, []);
} else if (scenario === "failed-leave") {
  const pending = hook.open("B");
  await Promise.resolve(); unmount(); gate.reject(new Error("Leave failed"));
  assert.equal(await pending, false); assert.deepEqual(events, []);
} else if (scenario === "pending-request") {
  holdRequest = true; editor.navigate = async () => {};
  const pending = hook.remove("A");
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.deepEqual(events, ["request:/A", "delete:A"]);
  unmount(); events.length = 0; pendingRequest.resolve();
  assert.equal(await pending, false); assert.deepEqual(events, []);
} else if (scenario === "pending-family-read") {
  holdFamilyRead = true; editor.navigate = async () => {};
  const pending = hook.remove("A");
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.deepEqual(events, ["request:/A"]);
  unmount(); events.length = 0; pendingRequest.resolve();
  assert.equal(await pending, false); assert.deepEqual(events, []);
} else if (scenario === "new-action-lock") {
  const old = hook.open("B");
  await Promise.resolve(); unmount(); remount();
  await new Promise<void>(resolve => setImmediate(resolve));
  const newerGate = deferred(), newer = hook.action(async () => newerGate.promise);
  gate.resolve(); assert.equal(await old, false);
  assert.equal(await hook.action(async () => { throw new Error("Must remain locked"); }), false);
  newerGate.resolve(); assert.equal(await newer, true);
} else if (scenario === "fresh-reopen") {
  gate.resolve(); await hook.fresh(); events.length = 0;
  assert.equal(await hook.open("B"), true);
  assert.deepEqual(events, ["request:/B", "request:/B/activate", "catalog", "url:/?project=B"]);
} else if (scenario === "template-open") {
  gate.resolve(); await hook.fresh(); events.length = 0;
  assert.equal(await hook.open("T"), true);
  assert.deepEqual(events, ["request:/T", "attach-template:T", "request:/T/activate", "catalog", "url:/?project=T"]);
  // Leaving a V7 opening drains and detaches its own editor, exactly like V1.
  hook.editor.current = null;
  hook.templateEditor.current = { background: true, navigate: async () => { events.push("template-navigate"); }, resume: async () => {}, refresh: async () => {},
    flush: async () => { throw new Error("Unexpected flush"); }, undo: () => {}, redo: () => {},
    applyAssistant: () => Promise.reject(new Error("Unexpected apply")), captureSelection: () => null, focusFinding: () => false };
  events.length = 0;
  assert.equal(await hook.open("B"), true);
  assert.deepEqual(events, ["template-navigate", "request:/B", "request:/B/activate", "catalog", "url:/?project=B"]);
} else if (scenario === "template-upload") {
  // A V7 .foldcv opens in the template editor with its own writer, like a V7 project from the list.
  gate.resolve(); await hook.fresh(); events.length = 0;
  assert.equal(await hook.upload(new File(["synthetic"], "project.foldcv")), true);
  assert.deepEqual(events, ["request:/v2/projects/archive", "attach-template:T", "url:/?project=T", "catalog"]);
  events.length = 0;
  assert.equal(await hook.archive("T", true), true);
  assert.ok(events.includes("v2-catalog:T:true"), "a newly opened V7 archive uses the v2 catalog route");
  assert.ok(!events.includes("request:/T/catalog/archive"));
} else throw new Error(`Unknown scenario ${scenario}`);
assert.equal(staleState, 0);
unmount();
