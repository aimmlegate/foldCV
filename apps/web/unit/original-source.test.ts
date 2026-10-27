import assert from "node:assert/strict";
import test from "node:test";
import { loadOriginal, originalKind, originalUrl } from "../src/workbench/editor/original-source";

test("original dispatch handles case, Markdown aliases and opaque identifiers", () => {
  assert.deepEqual(["resume.PDF", "resume.docx", "resume.TXT", "resume.md", "resume.MARKDOWN", "resume.html"].map(originalKind),
    ["pdf", "docx", "text", "markdown", "markdown", "unsupported"]);
  assert.equal(originalUrl("p/q", "s #"), "/v2/projects/p%2Fq/sources/s%20%23/original");
});

test("loading verifies exact bytes and rejects stale, missing or mismatched originals", async context => {
  const bytes = new TextEncoder().encode("# Original\r\n\r\n  spaces\tend");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hash = Buffer.from(digest).toString("hex");
  const controller = new AbortController();
  let status = 200;
  context.mock.method(globalThis, "fetch", (_url: string, options: RequestInit) => {
    assert.equal(options.credentials, "same-origin"); assert.equal(options.cache, "no-store");
    assert.equal(options.signal, controller.signal);
    return Promise.resolve(new Response(bytes, { status, headers: { "Content-Type": "text/markdown" } }));
  });
  const blob = await loadOriginal("/source", hash, controller.signal);
  assert.equal(await blob.text(), "# Original\r\n\r\n  spaces\tend");
  await assert.rejects(loadOriginal("/source", "0".repeat(64), controller.signal), /повреждён/);
  status = 404;
  await assert.rejects(loadOriginal("/source", hash, controller.signal), /загрузить/);
  status = 200; controller.abort();
  await assert.rejects(loadOriginal("/source", hash, controller.signal), { name: "AbortError" });
});
