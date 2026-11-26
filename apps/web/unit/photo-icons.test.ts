import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { halvings, pickProblem, pickLimit } from "../src/workbench/images/crop";
import { parseFocusIconChoices } from "../src/projects/api";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; if (url.endsWith(".css")) return { format: "module", source: "export default {}", shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { ImageDialog } = await import("../src/workbench/images/ImageDialog");
const { PhotoControl } = await import("../src/workbench/facts/PhotoControl");

test("a pick above 20 MB or not a raster image is refused before it is read; SVG is no input", () => {
  assert.equal(pickProblem({ size: pickLimit + 1, type: "image/jpeg" }), "Файл больше 20 МБ. Выберите файл меньше.");
  assert.match(pickProblem({ size: 10, type: "image/svg+xml" }) ?? "", /Это не изображение/u);
  assert.match(pickProblem({ size: 10, type: "application/pdf" }) ?? "", /Это не изображение/u);
  for (const type of ["image/jpeg", "image/png", "image/webp"]) assert.equal(pickProblem({ size: 10, type }), null);
});

test("a large reduction steps down by halves to the output size", () => {
  assert.deepEqual(halvings(4000, 800), [2000, 1000, 800]);
  assert.deepEqual(halvings(1000, 800), [800]);
  assert.deepEqual(halvings(256, 256), [256]);
});

test("the image dialog starts with a file pick, a disabled Save and Cancel; the photo frame has rounded corners", () => {
  const markup = renderToStaticMarkup(createElement(ImageDialog, { title: "Фото", output: { size: 800, type: "image/jpeg" as const }, rounded: true,
    save: async () => {}, close: () => {} }));
  assert.match(markup, /class="image-dialog rounded"/u);
  assert.match(markup, /Выбрать изображение/u);
  assert.match(markup, /accept="image\/jpeg,image\/png,image\/webp/u);
  assert.match(markup, /<button[^>]*disabled[^>]*>.*Сохранить/su);
  assert.match(markup, /Отмена/u);
  const icon = renderToStaticMarkup(createElement(ImageDialog, { title: "Своя иконка", output: { size: 256, type: "image/png" as const }, rounded: false,
    save: async () => {}, close: () => {} }));
  assert.match(icon, /class="image-dialog"/u);
});

test("Facts offers only a quiet «+ Фото» without a photo, and a picture with «Заменить» and remove with one", () => {
  const none = renderToStaticMarkup(createElement(PhotoControl, { photo: null, busy: false, setPhoto: async () => {} }));
  assert.match(none, />\+ Фото<\/button>/u);
  assert.ok(!none.includes("<img"));
  const shown = renderToStaticMarkup(createElement(PhotoControl, { photo: { url: "/v2/projects/p/images/abc", x: 21, top: 14, size: 61, radius: 7, shift: 73 },
    busy: true, setPhoto: async () => {} }));
  assert.match(shown, /<img class="fact-photo-preview" src="\/v2\/projects\/p\/images\/abc"/u);
  assert.match(shown, /<button[^>]*disabled[^>]*>Заменить<\/button>/u);
  assert.match(shown, /aria-label="Убрать фото"[^>]*disabled/u);
});

test("the icon choices take the own icons, and an older reply without them gives none", () => {
  const icon = { id: "react", names: ["react"], sha256: "a".repeat(64) };
  const own = { id: "own-" + "1".repeat(24), names: ["Своя"], sha256: "b".repeat(64) };
  assert.deepEqual(parseFocusIconChoices({ schemaVersion: 1, icons: [icon], rows: {}, own: [own] }).own, [own]);
  assert.deepEqual(parseFocusIconChoices({ schemaVersion: 1, icons: [icon], rows: {} }).own, []);
  assert.throws(() => parseFocusIconChoices({ schemaVersion: 1, icons: [], rows: {}, own: "x" }));
});
