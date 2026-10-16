import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import ts from "typescript";
import { BackgroundWriter } from "../src/background/writer";
import { sha256 } from "../src/background/wire";
import { deferred, harness, job, proposal, published, saved } from "./support/background-writer";

test("NB-G03:v03 a disposable late-adoption mutant fails the actual timeout regression", { timeout: 10000 }, async () => {
  const source = new URL("../src/background/writer.ts", import.meta.url), raw = await readFile(source, "utf8");
  const guard = 'if (ticket !== this.operation || this.mode !== "protected") throw new Error("WRITER_STALE_CALLBACK");';
  assert.equal(raw.split(guard).length, 2); assert.equal(raw.split("this.editor.queue.fencePrepared();").length, 2);
  const altered = raw.replace(guard, "void ticket;").replace("this.editor.queue.fencePrepared();", "");
  const root = await mkdtemp(join(tmpdir(), "foldcv-nb03-guard-"));
  try {
    await writeFile(join(root, "writer-mutant.ts"), altered);
    const compiled = ts.transpileModule(altered, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
    const linked = compiled.replace(/from (["'])(\.{1,2}\/[^"']+)\1/gu, (_match: string, _quote: string, path: string) =>
      `from ${JSON.stringify(new URL(`${path}.ts`, source).href)}`);
    const value: unknown = await import(`data:text/javascript;base64,${Buffer.from(linked).toString("base64")}`);
    assert.ok(typeof value === "object" && value !== null && "BackgroundWriter" in value && typeof value.BackgroundWriter === "function");
    const Mutant = value.BackgroundWriter as typeof BackgroundWriter;
    async function regression(writerClass: typeof BackgroundWriter, mutant: boolean) {
      const started = deferred<void>(), notice = deferred<void>(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
      const h = harness({ writerClass, onSaved: () => notice.resolve() });
      h.publishReply(() => { started.resolve(); return reply.promise; });
      const task = h.writer.publish(job, proposal);
      try {
        await started.promise; h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
        assert.ok(h.type("Post-timeout local input")); const buffer = new Map(h.mounted);
        reply.resolve({ schemaVersion: 1, job: saved, view: published });
        if (mutant) await notice.promise; else await h.settle();
        assert.equal(h.counts.notices, 0, "Late adoption must not announce the stale callback");
        assert.deepEqual(h.mounted, buffer); assert.equal(h.writer.mode, "recovering");
      } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await task.catch(() => {}); h.close(); }
    }
    await regression(BackgroundWriter, false);
    await assert.rejects(regression(Mutant, true), /Late adoption must not announce/u);
    process.stdout.write(`NB03 guard sensitivity ${JSON.stringify({ sourceSha256: await sha256(raw), mutantSha256: await sha256(altered),
      removed: [guard, "this.editor.queue.fencePrepared();"], healthy: "passed", mutant: "late-notice regression failed" })}\n`);
  } finally { await rm(root, { recursive: true }); }
});
