import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { zipSync } from "fflate";
import fixture from "../../../contracts/examples/render_request.json" with { type: "json" };
import type { RenderRequest } from "../src/contracts/generated/render_request";
import { render } from "../src/preview/render";

const raw: unknown = fixture;
const request = raw as RenderRequest;
const docx = Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1]);
const pdf = new TextEncoder().encode("%PDF synthetic");
function hash(bytes: Uint8Array): string { return createHash("sha256").update(bytes).digest("hex"); }
function archive(changes: Record<string, Uint8Array> = {}): Uint8Array {
  const metadata = {
    snapshotId: request.snapshot.id, projectRevision: request.snapshot.projectRevision,
    snapshotSha256: request.snapshot.snapshotSha256, templateId: request.snapshot.templateId,
    templateVersion: request.snapshot.templateVersion, templatePackageSha256: request.snapshot.templatePackageSha256,
    rendererVersion: request.snapshot.rendererVersion, rendererSha256: request.snapshot.rendererSha256,
    converterVersion: "26.2.6.3", converterSha256: "f".repeat(64), pageCount: 1,
    docxSha256: hash(docx), pdfSha256: hash(pdf),
    capabilities: { editableDocx: true, pdfDerivedFromDocx: true, embeddedPdfFonts: true },
  };
  return zipSync({ "resume.docx": docx, "resume.pdf": pdf,
    "render.json": new TextEncoder().encode(JSON.stringify(metadata)), ...changes });
}
function renameEntry(bytes: Uint8Array, previous: string, next: string): Uint8Array {
  const oldName = new TextEncoder().encode(previous);
  const newName = new TextEncoder().encode(next);
  assert.equal(oldName.length, newName.length);
  const copy = Uint8Array.from(bytes);
  let replaced = 0;
  for (let offset = 0; offset <= copy.length - oldName.length; offset += 1) {
    if (oldName.every((part, index) => copy[offset + index] === part)) {
      copy.set(newName, offset);
      replaced += 1;
    }
  }
  assert.equal(replaced, 2);
  return copy;
}
function changeDirectory(bytes: Uint8Array, change: (view: DataView, central: number, end: number) => void): Uint8Array {
  const copy = Uint8Array.from(bytes);
  const view = new DataView(copy.buffer);
  const end = copy.length - 22;
  const central = view.getUint32(end + 16, true);
  change(view, central, end);
  return copy;
}
async function withArchive(bytes: Uint8Array, check: () => Promise<void>): Promise<void> {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(Uint8Array.from(bytes), { headers: { "content-type": "application/zip" } });
  try { await check(); } finally { globalThis.fetch = original; }
}

test("only exact bounded archive entries and matching hashes install", async () => {
  await withArchive(archive(), async () => {
    const result = await render(request);
    assert.deepEqual(result.pdf, pdf);
    assert.deepEqual(result.docx, docx);
  });
  await withArchive(archive({ "extra.txt": new Uint8Array([1]) }), async () => {
    await assert.rejects(render(request));
  });
  await withArchive(archive({ "toString": new Uint8Array([1]) }), async () => {
    await assert.rejects(render(request));
  });
  await withArchive(renameEntry(archive({ duplicate0: pdf }), "duplicate0", "resume.pdf"), async () => {
    await assert.rejects(render(request));
  });
  await withArchive(archive({ "resume.pdf": new TextEncoder().encode("%PDF altered") }), async () => {
    await assert.rejects(render(request));
  });
});

test("actual expanded entry size is bounded even when compressed archive is small", async () => {
  const oversized = new Uint8Array(8 * 1024 * 1024 + 1);
  oversized.set(docx);
  await withArchive(archive({ "resume.docx": oversized }), async () => {
    await assert.rejects(render(request));
  });
});

test("central directory must describe the same exact three local entries", async () => {
  const baseline = archive();
  const malformed = [
    changeDirectory(baseline, (view, central) => {
      const nameStart = central + 46;
      new Uint8Array(view.buffer).set(new TextEncoder().encode("evilxx.pdf"), nameStart + 11 + 46);
    }),
    changeDirectory(baseline, (view, _central, end) => view.setUint16(end + 10, 2, true)),
    changeDirectory(baseline, (view, central) => view.setUint32(central + 42, 1, true)),
    changeDirectory(baseline, (view, central) => view.setUint32(central + 24, 99, true)),
    baseline.subarray(0, baseline.length - 1),
  ];
  for (const bytes of malformed) {
    await withArchive(bytes, async () => { await assert.rejects(render(request)); });
  }
});
