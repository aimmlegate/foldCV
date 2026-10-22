import assert from "node:assert/strict";
import { mock } from "node:test";
import type { RichEditorHandle } from "../src/rich/Editor";

function deferred() {
  let resolve: () => void = () => {}, reject: (error: Error) => void = () => {};
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const effects: (() => void | (() => void))[] = [], cleanups: (() => void)[] = [], events: string[] = [];
let mounted = true, staleState = 0;
Object.defineProperty(globalThis, "location", { value: { search: "?project=A", href: "http://foldcv.test/?project=A", pathname: "/" } });
Object.defineProperty(globalThis, "history", { value: { replaceState: (_data: unknown, _unused: string, url: string) => events.push(`url:${url}`) } });
mock.module("react", { namedExports: {
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void)) => { effects.push(effect); const cleanup = effect(); if (cleanup) cleanups.push(cleanup); },
  useRef: (current: unknown) => ({ current }),
  useState: (value: unknown): [unknown, () => void] => {
    const initial: unknown = typeof value === "function" ? Reflect.apply(value, null, []) : value;
    return [initial, () => { if (!mounted) staleState++; }];
  },
} });
const file = (path: string) => new URL(path, import.meta.url).href;
mock.module(file("../src/errors/messages.ts"), { namedExports: { errorMessage: (error: unknown) => String(error) } });
mock.module(file("../src/rich/import-source.ts"), { namedExports: { hasInput: () => false, importBody: () => ({}) } });
const pendingRequest = deferred();
let holdRequest = false;
mock.module(file("../src/rich/api.ts"), { namedExports: {
  deleteProject: async (id: string) => { events.push(`delete:${id}`); if (holdRequest) await pendingRequest.promise; return {}; },
  download: async () => new Blob(),
  listProjects: async () => { events.push("catalog"); return { entries: [] }; },
  request: async (path: string) => { events.push(`request:${path}`); return {}; },
  RichApiFailure: class extends Error {},
  projectRequest: async (path: string) => {
    events.push(`request:${path}`);
    return { workspace: { projectId: path === "/A" || path === "/A/activate" ? "A" : "B", project: {}, preDraft: null } };
  },
} });
mock.module(file("../src/background/connection.ts"), { namedExports: { attachExclusiveWriter: async () => null } });
mock.module(file("../src/background/fixed.ts"), { namedExports: { FixedOperations: class {} } });
mock.module(file("../src/background/api.ts"), { namedExports: { JobsApi: class {} } });
mock.module(file("../src/workbench/import/notices.ts"), { namedExports: { warningLabel: (value: unknown) => value } });
const { useResumeWorkspace } = await import("../src/workbench/useResumeWorkspace");
const hook = useResumeWorkspace();
await new Promise<void>(resolve => setImmediate(resolve));
events.length = 0;
const gate = deferred(), scenario = process.argv[2] ?? "";
const editor: RichEditorHandle = {
  background: true, sessionId: "session", navigate: () => gate.promise,
  resume: async () => { events.push("resume"); }, undo: () => {}, redo: () => {}, captureSelection: () => null,
  focusFinding: () => false, applyAssistant: async () => {},
  flush: async () => { throw new Error("Unexpected flush"); },
  assistantBaseline: async () => { throw new Error("Unexpected assistant baseline"); },
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
  hook.assistant.current = { stop: () => gate.promise, history: () => {}, fence: () => {} };
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
if (wait) {
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
  assert.deepEqual(events, ["delete:A"]);
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
} else throw new Error(`Unknown scenario ${scenario}`);
assert.equal(staleState, 0);
unmount();
