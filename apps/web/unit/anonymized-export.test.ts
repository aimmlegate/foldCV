import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { FileDialog } = await import("../src/workbench/files/FileDialog");
const { AnonymizedForm, checkLine } = await import("../src/workbench/files/AnonymizedForm");

const props = { mode: "export" as const, title: "Резюме", subtitle: "", filename: "x.docx", error: "", busy: false, close: () => {},
  download: async () => null, print: async () => true, upload: async () => true };
const anonymized = { preview: async () => ({ schemaVersion: 1 as const, name: "Alex E.", proposal: "Alex E.", leftOut: "Скрываем: телефон.",
  notices: [], removed: [], texts: {} }), download: async () => null, print: async () => true };

test("the export dialog offers DOCX, PDF and both anonymized items; without the anonymized export only the two", () => {
  const markup = renderToStaticMarkup(createElement(FileDialog, { ...props, anonymized }));
  const labels = [...markup.matchAll(/<strong>([^<]+)<\/strong>/gu)].map(match => match[1]);
  for (const label of ["DOCX", "PDF", "DOCX обезличенный", "PDF обезличенный"]) assert.ok(labels.includes(label), label);
  const plain = renderToStaticMarkup(createElement(FileDialog, props));
  assert.ok(!plain.includes("обезличенный") && plain.includes("Скачать DOCX"));
  // The present export keeps its button.
  assert.ok(markup.includes("Скачать DOCX"));
});

test("the places to check show at most five quotes, then «и ещё N», and nothing when there are none", () => {
  assert.equal(checkLine([]), "");
  assert.equal(checkLine(["a", "b"]), "Проверьте текст: «a», «b»");
  assert.equal(checkLine(["1", "2", "3", "4", "5", "6", "7", "2"]), "Проверьте текст: «1», «2», «3», «4», «5» и ещё 2");
});

test("the name form shows the name field with what the user typed, and an empty name stays empty", () => {
  const markup = renderToStaticMarkup(createElement(AnonymizedForm, { load: anonymized.preview, name: "", change: () => {}, busy: false }));
  // Before Python's answer the form waits; the field is not shown with a guessed name.
  assert.match(markup, /Готовим обезличенное резюме/u);
});

test("with Python's answer the form shows the name, what is left out and a subdued notice that blocks nothing", () => {
  const value = { ...await_value(), notices: [{ kind: "contact" as const, quote: "Пишите на …" }, { kind: "family" as const, quote: "Example City" }] };
  const markup = renderToStaticMarkup(createElement(AnonymizedForm, { load: anonymized.preview, name: "Alex E.", change: () => {}, busy: false, initial: value }));
  assert.match(markup, /<label for="anonymized-name">Имя в резюме<\/label><input id="anonymized-name"[^>]*value="Alex E."/u);
  assert.match(markup, /class="anonymized-left-out">Скрываем: телефон.</u);
  assert.match(markup, /class="anonymized-check" role="status">Проверьте текст: «Пишите на …», «Example City»</u);
  const empty = renderToStaticMarkup(createElement(AnonymizedForm, { load: anonymized.preview, name: "", change: () => {}, busy: false, initial: value }));
  assert.match(empty, /value=""/u);
  assert.ok(!renderToStaticMarkup(createElement(AnonymizedForm, { load: anonymized.preview, name: "x", change: () => {}, busy: false,
    initial: await_value() })).includes("Проверьте текст"));
});

function await_value() {
  return { schemaVersion: 1 as const, name: "Alex E.", proposal: "Alex E.", leftOut: "Скрываем: телефон.", notices: [], removed: [], texts: {} };
}
