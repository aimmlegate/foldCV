import assert from "node:assert/strict";
import { test } from "node:test";
import fixture from "../../../contracts/examples/render_request.json" with { type: "json" };
import type { RenderRequest } from "../src/contracts/generated/render_request";
import type { PrepareRequest } from "../src/contracts/generated/prepare_request";
import { syntheticProject } from "../src/editor/example";
import type { Rendered } from "../src/preview/render";
import { PreviewWorkflow } from "../src/preview/workflow";

const raw: unknown = fixture;
const prepared = raw as RenderRequest;
const input: PrepareRequest = { project: syntheticProject(), presentation: {
  name: "Мария Примерова", title: "Engineer", sourceLanguage: "en",
  jobProseBlocks: { job_1: "job_1_prose", job_2: "job_2_prose" },
} };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function tick() { await new Promise<void>((resolve) => setImmediate(resolve)); }
function artifact(request: RenderRequest): Rendered { return { request, pdf: new Uint8Array([1]), docx: new Uint8Array([2]) }; }
async function prepareMock(value: PrepareRequest): Promise<RenderRequest> {
  return { ...prepared, baseRevision: value.project.revision,
    snapshot: { ...prepared.snapshot, projectRevision: value.project.revision },
    document: { ...prepared.document, candidate: { ...prepared.document.candidate,
      name: value.presentation.name, title: value.presentation.title } } };
}

test("latest explicit request replaces an active snapshot; stale export never fires", async () => {
  const first = deferred<Rendered>();
  const second = deferred<Rendered>();
  const states: string[] = [];
  const exports: string[] = [];
  let calls = 0;
  const workflow = new PreviewWorkflow((state) => states.push(state.status), (_result, kind) => exports.push(kind),
    prepareMock,
    async () => { calls += 1; return calls === 1 ? first.promise : second.promise; });
  workflow.request(input, "pdf");
  await tick();
  assert.equal(calls, 1);
  workflow.invalidate();
  const newer = structuredClone(input);
  newer.project.revision += 1;
  workflow.request(newer, "docx");
  first.resolve(artifact({ ...prepared, baseRevision: input.project.revision }));
  await tick();
  assert.equal(calls, 2);
  assert.deepEqual(exports, []);
  second.resolve(artifact({ ...prepared, baseRevision: newer.project.revision }));
  await tick();
  assert.equal(workflow.ready?.request.baseRevision, newer.project.revision);
  assert.deepEqual(exports, ["docx"]);
  assert.equal(states.at(-1), "ready");
});

test("unapplied typing invalidates late result and cached repeat exports need no render", async () => {
  const pending = deferred<Rendered>();
  let calls = 0;
  const exports: string[] = [];
  const workflow = new PreviewWorkflow(() => {}, (_result, kind) => exports.push(kind), prepareMock,
    async () => { calls += 1; return calls === 1 ? pending.promise : artifact({ ...prepared, baseRevision: input.project.revision }); });
  workflow.request(input, "pdf");
  await tick();
  workflow.invalidate(); // The form changed before Apply.
  pending.resolve(artifact(prepared));
  await tick();
  assert.equal(workflow.ready, null);
  assert.deepEqual(exports, []);
  workflow.request(input, "docx");
  await tick();
  assert.equal(calls, 2);
  assert.deepEqual(exports, ["docx"]);
  workflow.request(input, "pdf");
  assert.equal(calls, 2);
  assert.deepEqual(exports, ["docx", "pdf"]);
});

test("failed render remains retryable only by another explicit request", async () => {
  let calls = 0;
  const states: string[] = [];
  const workflow = new PreviewWorkflow((state) => states.push(state.status), () => {}, prepareMock,
    async () => { calls += 1; if (calls === 1) throw new Error("bad archive"); return artifact(prepared); });
  workflow.request(input);
  await tick();
  assert.equal(calls, 1);
  assert.equal(states.at(-1), "error");
  workflow.request(input);
  await tick();
  assert.equal(calls, 2);
  assert.equal(states.at(-1), "ready");
});

test("cancelled draft restores exact validated bytes without another conversion", async () => {
  let calls = 0;
  const exports: Rendered[] = [];
  const workflow = new PreviewWorkflow(() => {}, (result) => exports.push(result), prepareMock,
    async (request) => { calls += 1; return artifact(request); });
  workflow.request(input);
  await tick();
  const first = workflow.ready;
  assert.ok(first);
  workflow.invalidate();
  assert.equal(workflow.ready, null);
  workflow.restore(input);
  assert.equal(workflow.ready, first);
  workflow.request(input, "pdf");
  assert.equal(calls, 1);
  assert.deepEqual(exports, [first]);
});

test("matching revision in a different project cannot reuse cached bytes", async () => {
  let calls = 0;
  const workflow = new PreviewWorkflow(() => {}, () => {}, prepareMock,
    async (request) => { calls += 1; return artifact(request); });
  workflow.request(input);
  await tick();
  const different = structuredClone(input);
  different.project.projectId = "different-project";
  workflow.invalidate();
  workflow.restore(different);
  assert.equal(workflow.ready, null);
  workflow.request(different);
  await tick();
  assert.equal(calls, 2);
});
