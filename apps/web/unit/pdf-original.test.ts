import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { removeNewerJavaScript } from "./support/old-webkit";

// A `?url` or `?worker&url` import gives the file's own address, as Vite gives the address of the built file.
register(`data:text/javascript,${encodeURIComponent('export async function resolve(specifier, context, next) { const [path, query] = specifier.split("?"); if (query !== "url" && query !== "worker&url") return next(specifier, context); const found = await next(path, context); return { ...found, url: found.url + "?address", shortCircuit: true }; } export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; if (url.endsWith("?address")) return { format: "module", source: "export default " + JSON.stringify(url.slice(0, -8)), shortCircuit: true }; return next(url, context); }')}`, import.meta.url);

test("the PDF original loads and reads a page on the JavaScript of Safari 16.4 (macOS 12–14)", async () => {
  removeNewerJavaScript();
  // The main build of pdf.js stopped here on macOS 14 («Can't find variable: Iterator») and took the whole window down.
  await import("../src/workbench/editor/PdfOriginal");
  // The page brings its own polyfills: the worker's do not reach it.
  assert.equal(typeof Reflect.get(Promise, "withResolvers"), "function");
  const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist/legacy/build/pdf.mjs");
  // The viewer set the worker, so this is the build it draws with, and the worker starts from the project's entry.
  assert.match(GlobalWorkerOptions.workerSrc, /\/src\/workbench\/editor\/pdf\.worker\.ts$/u);
  // A browser runs that entry in a worker; here it runs in this process and pdf.js finds it.
  await import(GlobalWorkerOptions.workerSrc);
  const fonts = fileURLToPath(new URL("../node_modules/pdfjs-dist/standard_fonts/", import.meta.url));
  const data = new Uint8Array(readFileSync(new URL("../../../tests/fixtures/synthetic/import/mixed-columns.pdf", import.meta.url)));
  const task = getDocument({ data, standardFontDataUrl: fonts });
  try {
    const pdf = await task.promise, page = await pdf.getPage(1);
    assert.equal(pdf.numPages, 4);
    // Drawing a page asks for this first; from Safari 18.4 to 26.1 the main build threw here, with no
    // Map.prototype.getOrInsertComputed.
    await pdf.getOptionalContentConfig();
    // The page has text, so its font goes through ArrayBuffer.prototype.transferToFixedLength.
    assert.ok((await page.getOperatorList()).fnArray.length > 0);
  } finally { await task.destroy(); }
});
