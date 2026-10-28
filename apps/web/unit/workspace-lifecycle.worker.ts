import assert from "node:assert/strict";
import { mock } from "node:test";
import type { TemplateEditorHandle } from "../src/rich/TemplateEditor";

function deferred() {
  let resolve: () => void = () => {}, reject: (error: Error) => void = () => {};
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const effects: (() => void | (() => void))[] = [], cleanups: (() => void)[] = [], events: string[] = [];
const scenario = process.argv[2] ?? "", importing = scenario.startsWith("import-");
// useState call order in useResumeWorkspace: the open template is the 1st state, error the 6th, busy the 8th.
const TEMPLATE = 0, ERROR = 5, BUSY = 7;
const stateWrites = new Map<number, unknown[]>(), initialStates = new Map<number, unknown>();
let stateIndex = 0, importReads = 0;
let mounted = true, staleState = 0;
Object.defineProperty(globalThis, "location", { value: { search: "?project=A", href: "http://foldcv.test/?project=A", pathname: "/" } });
Object.defineProperty(globalThis, "history", { value: { replaceState: (_data: unknown, _unused: string, url: string) => events.push(`url:${url}`) } });
mock.module("react", { namedExports: {
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void)) => { effects.push(effect); const cleanup = effect(); if (cleanup) cleanups.push(cleanup); },
  useRef: (current: unknown) => ({ current }),
  useState: (value: unknown): [unknown, (next: unknown) => void] => {
    const index = stateIndex++;
    const initial: unknown = initialStates.has(index) ? initialStates.get(index) : typeof value === "function" ? Reflect.apply(value, null, []) : value;
    return [initial, (next: unknown) => { if (!mounted) staleState++; stateWrites.set(index, [...stateWrites.get(index) ?? [], next]); }];
  },
} });
const file = (path: string) => new URL(path, import.meta.url).href;
mock.module(file("../src/errors/messages.ts"), { namedExports: { errorMessage: (error: unknown) => String(error) } });
mock.module(file("../src/rich/import-source.ts"), { namedExports: { hasInput: () => importing, importBody: () => ({}) } });
const pending = deferred();
let holdDelete = false, holdOpen = false, cleanupStatus = "complete";
const opened = (id: string) => ({ response: { workspace: { projectId: id, project: {} }, identity: null } });
mock.module(file("../src/workbench/open-editor.ts"), { namedExports: {
  openEditor: async (id: string) => { events.push(`open:${id}`); if (holdOpen) await pending.promise; return opened(id); },
} });
const queued = scenario === "import-queued";
const importState = scenario === "import-timeout" || queued ? "running" : scenario === "import-cancelled" ? "cancelled" : "failed";
mock.module(file("../src/projects/api.ts"), { namedExports: {
  listProjects: async () => { events.push("catalog"); return { entries: [], errors: [] }; },
  createProject: async () => { events.push("create"); return { workspace: { projectId: "T" } }; },
  startImport: async () => {
    if (!importing) throw new Error("unused");
    events.push("import:start");
    return { id: "task-1", state: importState, stage: queued ? "waiting" : "processing", detail: {},
      error: importState === "failed" ? "PROCESS_FAILED" : null };
  },
  projectTasks: async () => {
    importReads++;
    // The queued import waits 100 minutes behind another one, then runs.
    return [{ id: "task-1", state: "running", stage: queued && importReads <= 100 ? "waiting" : "processing", detail: {}, error: null }];
  },
  resumeImport: async () => { throw new Error("unused"); },
  cancelImport: async () => { events.push("import:cancel"); },
  openFoldcv: async () => {
    if (scenario !== "upload-archive") throw new Error("unused");
    events.push("request:/v2/projects/archive");
    return { workspace: { projectId: "T", project: {} }, identity: null };
  },
  deleteProject: async (id: string) => { events.push(`delete:${id}`); if (holdDelete) await pending.promise; return { cleanupStatus }; },
  catalogFlag: async (id: string, archived: boolean) => { events.push(`catalog-flag:${id}:${archived}`); },
} });
if (scenario === "export-refresh-failed") {
  initialStates.set(TEMPLATE, { response: opened("A").response, connection: { response: opened("A").response,
    exportDocx: async () => ({ blob: new Blob(["docx"]), attemptId: "attempt" }) } });
  Object.defineProperty(globalThis, "document", { value: { createElement: () => {
    const anchor = { href: "", download: "", click: () => events.push(`download:${anchor.download}`) };
    return anchor;
  } } });
}
const { useResumeWorkspace } = await import("../src/workbench/useResumeWorkspace");
const hook = useResumeWorkspace();
await new Promise<void>(resolve => setImmediate(resolve));
events.length = 0;
const gate = deferred();
const editor: TemplateEditorHandle = {
  background: true, navigate: () => gate.promise, resume: async () => { events.push("resume"); }, refresh: async () => {},
  flush: async () => { throw new Error("Unexpected flush"); }, undo: () => {}, redo: () => {},
  applyAssistant: () => Promise.reject(new Error("Unexpected apply")), captureSelection: () => null, focusFinding: () => false,
};
hook.templateEditor.current = editor;
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
  // One read per minute until the default import window plus cleanup (5 s), publication (158 s) and a minute.
  // A queued import gets the same window once it runs: the 100 minutes in the queue do not count.
  assert.equal(importReads, scenario === "import-timeout" ? 64 : queued ? 101 + 64 : 0);
  const expected = scenario === "import-timeout" || queued ? "PROCESS_TIMEOUT" : scenario === "import-cancelled" ? "CANCELLED" : "PROCESS_FAILED";
  assert.ok(stateWrites.get(ERROR)?.some(value => String(value).includes(expected)), "terminal imports report an error without an optional server error");
  assert.equal(stateWrites.get(BUSY)?.at(-1), false, "the busy state is released");
  assert.equal(await hook.action(async () => {}), true, "another action is admitted after failure");
  mock.restoreAll();
} else if (wait) {
  const result = invoke();
  await Promise.resolve(); unmount();
  if (wait === "remount") { remount(); await new Promise<void>(resolve => setImmediate(resolve)); }
  events.length = 0;
  gate.resolve();
  assert.equal(await result, action === "fresh" ? undefined : false);
  assert.deepEqual(events, []);
} else if (scenario === "failed-leave") {
  const result = hook.open("B");
  await Promise.resolve(); unmount(); gate.reject(new Error("Leave failed"));
  assert.equal(await result, false); assert.deepEqual(events, []);
} else if (scenario === "pending-delete") {
  holdDelete = true; editor.navigate = async () => {};
  const result = hook.remove("A");
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.deepEqual(events, ["delete:A"]);
  unmount(); events.length = 0; pending.resolve();
  assert.equal(await result, false); assert.deepEqual(events, []);
} else if (scenario === "pending-open") {
  holdOpen = true; editor.navigate = async () => {};
  const result = hook.open("B");
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.deepEqual(events, ["open:B"]);
  unmount(); events.length = 0; pending.resolve();
  assert.equal(await result, false); assert.deepEqual(events, []);
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
  assert.deepEqual(events, ["open:B", "catalog", "url:/?project=B"]);
} else if (scenario === "switch-open") {
  // Leaving an opened project drains and detaches its editor before the next one opens.
  gate.resolve(); await hook.fresh(); events.length = 0;
  assert.equal(await hook.open("T"), true);
  assert.deepEqual(events, ["open:T", "catalog", "url:/?project=T"]);
  hook.templateEditor.current = { ...editor, navigate: async () => { events.push("template-navigate"); } };
  events.length = 0;
  assert.equal(await hook.open("B"), true);
  assert.deepEqual(events, ["template-navigate", "open:B", "catalog", "url:/?project=B"]);
} else if (scenario === "delete-cleanup-failed") {
  // The project is deleted, but some of its files remain; the service reports "failed" and the action says so.
  cleanupStatus = "failed"; editor.navigate = async () => {};
  assert.equal(await hook.remove("A"), false);
  assert.ok(events.includes("delete:A"));
  assert.ok(stateWrites.get(ERROR)?.some(value => String(value).includes("PROJECT_CLEANUP_INCOMPLETE")));
} else if (scenario === "export-refresh-failed") {
  // The refresh after the export record fails; the downloaded file is still delivered and the action succeeds.
  editor.flush = async () => opened("A").response as never;
  editor.refresh = async () => { throw new Error("REFRESH_FAILED"); };
  assert.equal(await hook.exportFile("export", "resume.docx"), true);
  assert.deepEqual(events, ["download:resume.docx"]);
  assert.ok(!stateWrites.get(ERROR)?.some(Boolean));
} else if (scenario === "upload-archive") {
  // A .foldcv opens through v2 and takes its own editor token, like a project from the list.
  gate.resolve(); await hook.fresh(); events.length = 0;
  assert.equal(await hook.upload(new File(["synthetic"], "project.foldcv")), true);
  assert.deepEqual(events, ["request:/v2/projects/archive", "open:T", "url:/?project=T", "catalog"]);
  events.length = 0;
  assert.equal(await hook.archive("T", true), true);
  assert.ok(events.includes("catalog-flag:T:true"));
} else throw new Error(`Unknown scenario ${scenario}`);
assert.equal(staleState, 0);
unmount();
