import assert from "node:assert/strict";
import test from "node:test";
import { DraftRepository, draftLimits, type LocalDraft } from "../src/background/drafts";
import { sha256 } from "../src/background/wire";
import { validateBackgroundShape } from "../src/contracts/background-validate";
import { deferred, MemoryDraftDatabase, before, proof } from "./support/background-writer";

async function record(sequence = 1): Promise<LocalDraft> {
  const project = before.response.workspace.project; assert.ok(project);
  const payloadWire = JSON.stringify({ schemaVersion: 1, document: project.document, facts: project.facts, outbox: [],
    historyOutbox: [], touches: [], assetPins: [] });
  return { schemaVersion: 1, project: before.response.workspace.projectId, lineage: proof.lineage, epoch: proof.epoch,
    incarnation: proof.incarnation, id: "local-recovery", sequence, cursor: sequence, baseRevision: before.response.workspace.projectRevision,
    baseSha256: before.workspaceSha256, payloadWire, payloadSha256: await sha256(payloadWire), assets: [] };
}

async function sizedRecord(bytes: number, projectId = before.response.workspace.projectId): Promise<LocalDraft> {
  const source = before.response.workspace.project; assert.ok(source);
  const document = structuredClone(source.document), sample = document.regions.flatMap(region => region.blocks).find(block => block.type === "paragraph");
  assert.ok(sample && Array.isArray(sample.content));
  const first = sample.content[0]; assert.ok(first && first.type === "text");
  const payload = { schemaVersion: 1, document, facts: source.facts, outbox: [], touches: [], assetPins: [], historyOutbox: [] };
  const row = { ...await record(2), project: projectId, payloadWire: JSON.stringify(payload) };
  const size = () => { row.payloadWire = JSON.stringify(payload); return new TextEncoder().encode(JSON.stringify(row)).length; };
  let count = 0;
  while (size() < bytes - 20000) {
    document.regions[2].blocks.push({ ...structuredClone(sample), id: `padding-${String(count++)}`,
      content: [{ ...first, text: "x".repeat(12000) }] });
  }
  const padding = { ...structuredClone(sample), id: `padding-${String(count)}`, content: [{ ...first, text: "" }] };
  document.regions[2].blocks.push(padding);
  const span = padding.content[0]; assert.ok(span);
  const remainder = bytes - size(); assert.ok(remainder >= 0 && remainder <= 20000); span.text = "x".repeat(remainder);
  assert.equal(size(), bytes);
  assert.ok(validateBackgroundShape("background_draft_payload_v1", payload));
  row.payloadSha256 = await sha256(row.payloadWire);
  return row;
}

for (const [index, fault] of ["quota", "rejected", "partial", "unsupported", "missing-blob", "wrong-project", "late-checkpoint", "corrupt"].entries()) {
  test(`NB-W11:v${String(index + 1).padStart(2, "0")} local draft ${fault} preserves the retained record and watermark`, async () => {
    const database = new MemoryDraftDatabase(), original = await record(), bytes = new TextEncoder().encode("Pinned synthetic image");
    const repository = new DraftRepository(database, () => Promise.resolve(bytes));
    await repository.write(original);
    if (fault === "quota" || fault === "rejected") {
      database.failure = new Error(fault === "quota" ? "QuotaExceededError" : "Write rejected");
      await assert.rejects(repository.write(await record(2))); database.failure = null;
      assert.deepEqual((await repository.read(original.project, original.lineage))?.record, original);
    } else if (fault === "late-checkpoint") {
      const held = deferred<Uint8Array<ArrayBuffer>>(), reached = deferred<void>();
      let calls = 0;
      const ordered = new DraftRepository(database, () => { calls++; if (calls === 1) { reached.resolve(); return held.promise; } return Promise.resolve(bytes); });
      const asset = { id: "synthetic-image", sha256: await sha256(bytes) };
      const older = { ...await record(2), assets: [asset] }, newer = { ...await record(3), assets: [asset] };
      const first = ordered.write(older); await reached.promise; await ordered.write(newer);
      held.resolve(bytes); assert.equal((await first).sequence, 3);
      const fresh = new DraftRepository(database, () => Promise.resolve(bytes));
      assert.equal((await fresh.read(original.project, original.lineage))?.record.cursor, 3);
    } else if (fault === "missing-blob") {
      const row = { ...await record(2), assets: [{ id: "gone", sha256: await sha256(bytes) }] };
      await repository.write(row);
      const missing = new DraftRepository(database, () => Promise.reject(new Error("Missing blob")));
      await assert.rejects(missing.read(row.project, row.lineage), /Missing blob/u);
      assert.equal(database.rows[0]?.sequence, 2);
    } else if (fault === "wrong-project") {
      const wrong = { ...original, project: "other-project" }; database.rows = [wrong];
      assert.equal(await repository.read(original.project, original.lineage), null);
      await assert.rejects(repository.read(wrong.project, "other-lineage"), /DRAFT_CORRUPT/u);
      assert.deepEqual(database.rows, [wrong]);
    } else {
      const bad = structuredClone(original);
      if (fault === "unsupported") Object.assign(bad, { schemaVersion: 2 });
      else if (fault === "partial") bad.payloadWire = '{"schemaVersion":1}';
      else bad.payloadWire += "changed";
      if (fault === "partial") bad.payloadSha256 = await sha256(bad.payloadWire);
      database.rows = [bad];
      await assert.rejects(repository.read(original.project, original.lineage), /DRAFT_CORRUPT/u);
      assert.deepEqual(database.rows, [bad]);
    }
  });
}

test("a failed deletion cannot remove a newer local buffer", async () => {
  const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
  const older = await record(1), newer = await record(2);
  await repository.write(older); await repository.write(newer);
  await assert.rejects(repository.remove(older), /DRAFT_CHANGED/u);
  assert.equal((await repository.read(older.project, older.lineage))?.record.sequence, 2);
});

test("a returning old epoch keeps its draft without replacing the new writer buffer", async () => {
  const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
  const old = await record(1), next = { ...await record(2), epoch: old.epoch + 1, id: "next-owner" };
  await repository.write(old); await repository.write(next); await repository.write({ ...old, sequence: 3, cursor: 3 });
  assert.equal(database.rows.length, 2);
  assert.equal((await repository.read(old.project, old.lineage))?.record.epoch, next.epoch);
  await repository.remove(next);
  assert.equal((await repository.read(old.project, old.lineage))?.record.sequence, 3);
});

test("a resumed connection selects its own durable input even after the old connection writes a larger sequence", async () => {
  const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
  const old = await record(10), current = { ...await record(2), incarnation: "resumed-connection" };
  await repository.write(old); await repository.write(current); await repository.write({ ...old, sequence: 11, cursor: 11 });
  const retained = await repository.read(current.project, current.lineage, { epoch: current.epoch, incarnation: current.incarnation });
  assert.equal(retained?.record.sequence, 2); assert.equal(database.rows.length, 2);
  await repository.remove(old).catch(() => {});
  assert.equal(database.rows.length, 2);
});

test("explicit owner replacement is atomic and refuses a draft that changed after review", async () => {
  const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
  const old = await record(), next = { ...old, epoch: old.epoch + 1, id: "resolved-owner", sequence: 1, cursor: 0 };
  await repository.write(old); await repository.replaceOwner(old, next);
  assert.deepEqual(database.rows, [next]);
  const newer = { ...next, sequence: 2, cursor: 1 }; await repository.write(newer);
  await assert.rejects(repository.replaceOwner(next, { ...next, epoch: next.epoch + 1 }), /DRAFT_CHANGED/u);
  assert.deepEqual(database.rows, [newer]);
});

for (const [index, offset] of [-1, 0, 1].entries()) {
  test(`NB-A04:v${String(index + 31)} valid local draft bytes at boundary ${String(offset)} retain the prior buffer on rejection`, async () => {
    const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
    const first = await record(); await repository.write(first);
    const full = await sizedRecord(draftLimits.project + offset);
    if (offset > 0) {
      await assert.rejects(repository.write(full), /DRAFT_STORAGE_FULL/u);
      assert.equal((await repository.read(first.project, first.lineage))?.record.sequence, 1);
    } else {
      await repository.write(full); assert.equal((await repository.read(first.project, first.lineage))?.record.sequence, 2);
    }
  });
}

test("the global draft cap rejects another project without evicting four full project buffers", async () => {
  const database = new MemoryDraftDatabase(), repository = new DraftRepository(database, () => Promise.reject(new Error("Unused")));
  for (let index = 0; index < 4; index++) await repository.write(await sizedRecord(draftLimits.project, `project-${String(index)}`));
  const retained = structuredClone(database.rows);
  await assert.rejects(repository.write(await sizedRecord(draftLimits.project, "project-five")), /DRAFT_STORAGE_FULL/u);
  assert.deepEqual(database.rows, retained);
});
