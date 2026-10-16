import { readFileSync, writeFileSync, renameSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));

function encode(value) {
  return JSON.stringify(value, (_key, item) => item instanceof Error
    ? { name: item.name, message: item.message, stack: item.stack, ...item } : typeof item === "bigint" ? String(item) : item);
}

export default async function* report(source) {
  const contextFile = process.env.FOLDCV_BACKGROUND_NODE_CONTEXT;
  const context = contextFile ? JSON.parse(readFileSync(contextFile, "utf8")) : null;
  const path = context?.reportPath;
  const records = [], collected = [], raw = [], parents = new Map(), enqueued = new Map(), started = new Map(), containers = new Map();
  let failures = 0;
  const location = data => `${relative(root, resolve(data.file ?? "missing-file"))}:${data.line ?? 0}:${data.column ?? 0}:${data.nesting}:${data.name}`;
  function identity(data, starting) {
    const file = relative(root, resolve(data.file ?? "missing-file")).split("\\").join("/");
    const stack = parents.get(file) ?? [];
    if (starting) { stack.length = data.nesting; stack.push(data.name); parents.set(file, stack); }
    if (stack[data.nesting] !== data.name) throw new Error("Node reporter cannot resolve the exact parent test");
    return file + "::" + stack.slice(0, data.nesting + 1).join("::");
  }
  const save = complete => {
    if (!context || !path) return;
    const { reportPath: _reportPath, ...scope } = context;
    const body = { schemaVersion: 1, ...scope, finishedAt: new Date().toISOString(), complete,
      exitStatus: failures ? 1 : 0, collected, records, traces: [] };
    writeFileSync(path + ".events.jsonl", raw.join("\n") + "\n");
    writeFileSync(path + ".pending", JSON.stringify(body, null, 2) + "\n"); renameSync(path + ".pending", path);
  };
  try {
    save(false);
    for await (const event of source) {
      raw.push(encode(event));
      const data = event.data;
      if (event.type === "test:enqueue") enqueued.set(location(data), (enqueued.get(location(data)) ?? 0) + 1);
      if (event.type === "test:complete" && data.details?.passed === true && data.nesting === 0
          && data.line === 1 && data.column === 1 && data.file && resolve(data.name) === resolve(data.file)) {
        containers.set(location(data), (containers.get(location(data)) ?? 0) + 1);
      }
      if (event.type === "test:start") {
        const node = identity(data, true);
        collected.push(node); started.set(location(data), (started.get(location(data)) ?? 0) + 1);
        yield `# Subtest: ${data.name}\n`;
      }
      if (event.type === "test:pass" || event.type === "test:fail") {
        const node = identity(data, false), passed = event.type === "test:pass", markers = [];
        if (data.skip !== undefined) markers.push("skip");
        if (data.todo !== undefined) markers.push("todo");
        if (!passed) failures++;
        // Node emits a terminal pass only after its before/after hooks finish.
        records.push({ nodeId: node, phases: data.skip !== undefined ? { setup: "skipped", call: "skipped", teardown: "skipped" }
          : passed ? { setup: "passed", call: "passed", teardown: "passed" }
          : { setup: "unknown", call: data.details?.error?.failureType === "testCodeFailure" ? "failed" : "unknown", teardown: "unknown" }, markers, attempt: 1 });
        yield `${passed ? "ok" : "not ok"} ${records.length} - ${data.name}\n`;
        if (!passed) yield `# ${encode(data.details?.error)}\n`;
      }
    }
    if ([...enqueued].some(([key, count]) => (started.get(key) ?? containers.get(key)) !== count)
      || [...started].some(([key, count]) => enqueued.get(key) !== count)) failures++;
    if (records.length !== collected.length || !records.length) failures++;
    save(true);
    yield `# tests ${records.length}\n# fail ${failures}\n`;
  } catch (error) { failures++; save(false); throw error; }
}
