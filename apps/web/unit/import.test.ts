import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import firstFixture from "../../../contracts/examples/extract_result.json" with { type: "json" };
import secondFixture from "../../../contracts/examples/notes_extract_result.json" with { type: "json" };
import { validateExtractResult } from "../src/contracts/validate";
import { ImportWorkflow } from "../src/import/workflow";

const root = resolve(import.meta.dirname, "../../..");
const firstBytes = Uint8Array.from(readFileSync(resolve(root, "tests/fixtures/synthetic/import/unicode.txt")));
const secondBytes = Uint8Array.from(readFileSync(resolve(root, "tests/fixtures/synthetic/import/notes.md")));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => { resolve = yes; });
  return { promise, resolve };
}

function response(value: unknown, status = 200): Response {
  const names: Record<string, string> = {
    pdf: "source.pdf", docx: "source.docx", txt: "source.txt", markdown: "source.md", paste: "pasted.txt",
  };
  const transportName = value !== null && typeof value === "object" && "sourceKind" in value
    ? names[String(value.sourceKind)] : undefined;
  const transported = transportName && value !== null && typeof value === "object"
    ? { ...value, originalName: transportName } : value;
  return new Response(JSON.stringify(transported), { status, headers: { "Content-Type": "application/json" } });
}

async function tick(): Promise<void> { await new Promise<void>((resolve) => setImmediate(resolve)); }

function file(bytes: Uint8Array, name: string): File {
  return new File([Uint8Array.from(bytes)], name);
}

test("generated extraction contract validates source metadata and rejects broken order", () => {
  assert.equal(validateExtractResult(firstFixture), true);
  const broken = structuredClone(firstFixture);
  broken.units[0]!.order = 8;
  assert.equal(validateExtractResult(broken), false);
  const badHash = structuredClone(firstFixture);
  badHash.byteSha256 = "invalid";
  assert.equal(validateExtractResult(badHash), false);
});

test("new selection, cancellation and project replacement discard late imports", async () => {
  const first = deferred<Response>();
  const second = deferred<Response>();
  const third = deferred<Response>();
  const queue = [first, second, third];
  const workflow = new ImportWorkflow(() => {}, async () => {
    const next = queue.shift();
    if (!next) throw new Error("unexpected request");
    return next.promise;
  });
  const old = workflow.file(file(firstBytes, "unicode.txt"));
  await tick();
  const newer = workflow.file(file(secondBytes, "notes.md"));
  await tick();
  first.resolve(response(firstFixture));
  await old;
  assert.equal(workflow.state.entries.length, 0);
  second.resolve(response(secondFixture));
  await newer;
  assert.equal(workflow.state.entries[0]?.result.originalName, "notes.md");
  const pending = workflow.file(file(firstBytes, "unicode.txt"));
  await tick();
  workflow.cancel();
  third.resolve(response(firstFixture));
  await pending;
  assert.equal(workflow.state.entries.length, 1);
  assert.equal(workflow.state.entries[0]?.result.originalName, "notes.md");
  workflow.clear();
  assert.equal(workflow.state.entries.length, 0);
  assert.equal(workflow.original(secondFixture.sourceId), null);
});

test("original bytes and user overlays survive a failed replacement independently", async () => {
  let count = 0;
  const workflow = new ImportWorkflow(() => {}, async () => {
    count += 1;
    return count === 1 ? response(firstFixture) : response({ error: { code: "EXTRACT_MALFORMED" } }, 422);
  });
  await workflow.file(file(firstBytes, "unicode.txt"));
  assert.equal(workflow.state.entries.length, 1);
  workflow.overlay(firstFixture.sourceId, "unit:unit_1", "Мой исправленный текст");
  const copy = workflow.original(firstFixture.sourceId);
  assert.ok(copy);
  assert.deepEqual(copy, firstBytes);
  copy[0] = 0;
  assert.deepEqual(workflow.original(firstFixture.sourceId), firstBytes);
  await workflow.file(file(secondBytes, "notes.md"));
  assert.equal(workflow.state.entries.length, 1);
  assert.equal(workflow.state.entries[0]?.overlays["unit:unit_1"], "Мой исправленный текст");
  assert.equal(workflow.state.entries[0]?.result.units[0]?.text, "Привет\r\n");
  assert.match(workflow.state.error ?? "", /повреждён/);
});

test("renaming compatible bytes keeps overlays; changed extraction cannot erase them", async () => {
  const renamed = { ...firstFixture, originalName: "renamed.txt" };
  const changed = { ...firstFixture, originalName: "renamed.txt",
    units: firstFixture.units.map((unit, index) => index === 0 ? { ...unit, text: "changed" } : unit) };
  const responses = [firstFixture, renamed, changed];
  const workflow = new ImportWorkflow(() => {}, async () => response(responses.shift()));
  await workflow.file(file(firstBytes, "unicode.txt"));
  workflow.overlay(firstFixture.sourceId, "unit:unit_1", "User correction");
  await workflow.file(file(firstBytes, "renamed.txt"));
  assert.equal(workflow.state.entries[0]?.result.originalName, "renamed.txt");
  assert.equal(workflow.state.entries[0]?.overlays["unit:unit_1"], "User correction");
  await workflow.file(file(firstBytes, "renamed.txt"));
  assert.equal(workflow.state.entries[0]?.result.units[0]?.text, "Привет\r\n");
  assert.equal(workflow.state.entries[0]?.overlays["unit:unit_1"], "User correction");
  assert.match(workflow.state.error ?? "", /прочитан иначе/);
  workflow.overlay(firstFixture.sourceId, "unit:missing", "untrusted");
  assert.equal(workflow.state.entries[0]?.overlays["unit:missing"], undefined);
  workflow.overlay(firstFixture.sourceId, "gap:999", "untrusted");
  assert.equal(workflow.state.entries[0]?.overlays["gap:999"], undefined);
  workflow.overlay(firstFixture.sourceId, "unit:unit_1", "x".repeat(65 * 1024));
  assert.equal(workflow.state.entries[0]?.overlays["unit:unit_1"], "User correction");
  assert.match(workflow.state.error ?? "", /64 КБ/);
});

test("quoted and percent-marked names use safe transport while retaining the exact display name", async () => {
  const transmitted: string[] = [];
  const workflow = new ImportWorkflow(() => {}, async (_input, init) => {
    const body = init?.body;
    assert.ok(body instanceof FormData);
    const selected = body.get("file");
    assert.ok(selected instanceof File);
    transmitted.push(selected.name);
    return response(firstFixture);
  });
  await workflow.file(file(firstBytes, 'resume "draft".txt'));
  workflow.overlay(firstFixture.sourceId, "unit:unit_1", "manual text");
  await workflow.file(file(firstBytes, "resume %22draft%22.txt"));
  assert.deepEqual(transmitted, ["source.txt", "source.txt"]);
  assert.equal(workflow.state.entries.length, 1);
  assert.equal(workflow.state.entries[0]?.result.originalName, "resume %22draft%22.txt");
  assert.equal(workflow.state.entries[0]?.overlays["unit:unit_1"], "manual text");
  assert.deepEqual(workflow.original(firstFixture.sourceId), firstBytes);
});

test("aggregate source and response bounds preserve accepted work", async () => {
  let calls = 0;
  const workflow = new ImportWorkflow(() => {}, async (_input, init) => {
    calls += 1;
    if (calls === 12) return new Response(new Uint8Array(4 * 1024 * 1024 + 1),
      { headers: { "Content-Type": "application/json" } });
    const form = init?.body;
    assert.ok(form instanceof FormData);
    const selected = form.get("file");
    assert.ok(selected instanceof Blob);
    const bytes = new Uint8Array(await selected.arrayBuffer());
    const name = selected instanceof File ? selected.name : "source.txt";
    const hash = createHash("sha256").update(bytes).digest("hex");
    return response({ ...firstFixture, originalName: name, byteLength: bytes.length, byteSha256: hash,
      byteRef: `memory:sha256:${hash}`, sourceId: `source_${hash.slice(0, 24)}` });
  });
  for (let index = 0; index < 11; index += 1) await workflow.file(file(new TextEncoder().encode(`source-${index}`), `source-${index}.txt`));
  assert.equal(workflow.state.entries.length, 10);
  assert.match(workflow.state.error ?? "", /10 файлов/);
  await workflow.file(file(firstBytes, "unicode.txt"));
  assert.equal(workflow.state.entries.length, 10);
  assert.match(workflow.state.error ?? "", /Ответ извлечения слишком большой/);
});
