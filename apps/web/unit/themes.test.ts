import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { colorTokens, contrastRatio, palette, themes, toHex, toOklch, type ThemeId } from "../src/workbench/settings/themes";
import { applyAppearance, contrastRange, glassRange, initialAppearance, readAppearance, resolveMode, storeAppearance, type AppearanceRoot } from "../src/workbench/settings/interface";

const here = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const hex = /^#[0-9a-f]{6}$/;
function parseTokens(css: string): Record<string, string> {
  return Object.fromEntries([...css.matchAll(/--([a-z-]+):\s*([^;}]+)/g)].map(match => [match[1] ?? "", (match[2] ?? "").trim()]));
}

test("the prototype tokens and the sheet's pinned values are the FoldCV light palette at 100 %", () => {
  const light = palette("foldcv", "light", 100);
  for (const file of ["../../../design/future-editor/visual/tokens.css", "../src/workbench/styles/sheet-light.css"]) {
    const tokens = parseTokens(here(file));
    for (const [token, value] of Object.entries(light)) assert.equal(tokens[token], value, `${file} --${token}`);
  }
  // The approved prototype colors show unchanged by default.
  assert.deepEqual([light.paper, light.ink, light.muted, light.line, light.accent, light.wash], ["#fffefa", "#1c2119", "#47513f", "#dfe2d6", "#58684c", "#e8eddf"]);
});

test("every theme reads on both sides: text, captions and buttons keep WCAG ratios", () => {
  for (const theme of themes) for (const mode of ["light", "dark"] as const) {
    const colors = palette(theme.id, mode, 100), name = `${theme.id} ${mode}`;
    for (const token of colorTokens) assert.match(colors[token], hex, `${name} ${token}`);
    for (const token of ["shade", "paper-rgb", "accent-rgb"] as const) assert.match(colors[token], /^\d{1,3} \d{1,3} \d{1,3}$/, `${name} ${token}`);
    assert.ok(contrastRatio(colors.ink, colors.paper) >= 10, `${name} ink`);
    assert.ok(contrastRatio(colors.muted, colors.paper) >= 7, `${name} muted`);
    assert.ok(contrastRatio(colors["accent-text"], colors.paper) >= 4.5, `${name} accent text`);
    assert.ok(contrastRatio(colors["on-accent"], colors.accent) >= 4.5, `${name} on accent`);
    assert.ok(contrastRatio(colors.warn, colors.paper) >= 4.5 && contrastRatio(colors.danger, colors.paper) >= 4.5, `${name} warn and danger`);
    const l = (value: string) => toOklch(value).l, lighter = mode === "dark" ? 1 : -1;
    // Surfaces sit below the paper, content on the other side, in a fixed order.
    assert.ok(l(colors.desk) < l(colors.nav) && l(colors.nav) < l(colors.surface) && l(colors.surface) < l(colors.paper), `${name} surfaces`);
    const steps = ["wash", "wash-strong", "line", "line-strong", "faint", "muted-soft", "muted", "ink"] as const;
    for (let index = 1; index < steps.length; index += 1) {
      const previous = steps[index - 1], current = steps[index];
      assert.ok(previous && current && (l(colors[current]) - l(colors[previous])) * lighter > 0, `${name} ${String(previous)} before ${String(current)}`);
    }
  }
});

test("contrast bends the distances from the paper: lines and captions move most, the paper stays, nothing clips", () => {
  for (const mode of ["light", "dark"] as const) {
    const soft = palette("foldcv", mode, 50), plain = palette("foldcv", mode, 100), strong = palette("foldcv", mode, 150), top = palette("foldcv", mode, 200);
    assert.equal(soft.paper, plain.paper); assert.equal(top.paper, plain.paper);
    const ratio = (colors: typeof plain, token: "ink" | "line" | "muted") => contrastRatio(colors[token], colors.paper);
    assert.ok(ratio(soft, "ink") < ratio(plain, "ink") && ratio(plain, "ink") < ratio(strong, "ink") && ratio(strong, "ink") < ratio(top, "ink"), mode);
    assert.ok(ratio(strong, "line") > ratio(plain, "line") * 1.3, `${mode} lines firmer`);
    assert.ok(ratio(top, "line") > ratio(strong, "line"), `${mode} lines firmer still`);
    assert.notEqual(top.ink, top.muted, `${mode} ink and muted stay apart at 200 %`);
    assert.ok(![top.ink, top.muted].includes("#000000") && ![top.ink, top.muted].includes("#ffffff"), mode);
  }
  assert.deepEqual(palette("ocean", "dark", 300), palette("ocean", "dark", contrastRange.maximum));
  assert.deepEqual(palette("ocean", "dark", 10), palette("ocean", "dark", contrastRange.minimum));
});

test("color conversion round-trips and keeps out-of-gamut colors by shrinking chroma", () => {
  for (const value of ["#1c2119", "#fffefa", "#58684c", "#8b4230", "#0e7195"]) assert.equal(toHex(toOklch(value)), value);
  const vivid = toHex({ l: 0.6, c: 0.4, h: 30 });
  assert.match(vivid, hex); assert.ok(Math.abs(toOklch(vivid).l - 0.6) < 0.01);
  assert.ok(contrastRatio("#000000", "#ffffff") > 20.9 && contrastRatio("#ffffff", "#000000") > 20.9);
});

type Store = Record<string, string>;
function withStorage(store: Store, run: () => void) {
  const fake = { getItem: (key: string) => store[key] ?? null, setItem: (key: string, value: string) => { store[key] = value; } };
  const previous = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { value: fake, configurable: true, writable: true });
  try { run(); } finally {
    if (previous) Object.defineProperty(globalThis, "localStorage", previous); else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
}
function fakeRoot(): AppearanceRoot & { properties: Record<string, string> } {
  const properties: Record<string, string> = {};
  return { dataset: {}, properties, style: { colorScheme: "", setProperty: (name, value) => { properties[name] = value; } } };
}

test("saved choices read back, the old high contrast becomes 130 %, and bad values fall back", () => {
  withStorage({}, () => assert.deepEqual(readAppearance(), initialAppearance));
  withStorage({ "foldcv.interface.contrast": "high", "foldcv.interface.text-size": "large" }, () => {
    assert.deepEqual(readAppearance(), { ...initialAppearance, contrast: 130, textSize: "large" });
  });
  withStorage({ "foldcv.interface.contrast": "999", "foldcv.interface.glass": "abc", "foldcv.interface.scheme": "blue", "foldcv.interface.theme-light": "nope" }, () => {
    assert.deepEqual(readAppearance(), initialAppearance);
  });
  const store: Store = {};
  withStorage(store, () => {
    const root = fakeRoot();
    const chosen = { textSize: "x-large" as const, scheme: "dark" as const, lightTheme: "ocean" as ThemeId, darkTheme: "iris" as ThemeId, contrast: 125, glass: glassRange.minimum };
    applyAppearance(chosen, root, false); storeAppearance({ ...chosen });
    assert.deepEqual(readAppearance(), chosen);
    assert.equal(store["foldcv.interface.theme-dark"], "iris"); assert.equal(store["foldcv.interface.contrast"], "125");
  });
});

test("applying the appearance marks the root and writes the resolved palette", () => {
  const root = fakeRoot();
  assert.equal(applyAppearance({ ...initialAppearance, scheme: "system" }, root, true), "dark");
  assert.equal(root.dataset["mode"], "dark"); assert.equal(root.dataset["theme"], "foldcv"); assert.equal(root.style.colorScheme, "dark");
  assert.equal(root.properties["--paper"], palette("foldcv", "dark", 100).paper); assert.equal(root.properties["--glass"], "0.95");
  assert.equal(root.dataset["uiContrast"], undefined); assert.equal(root.dataset["uiText"], undefined);
  assert.equal(applyAppearance({ ...initialAppearance, scheme: "system", lightTheme: "rose", contrast: 125, textSize: "large", glass: 60 }, root, false), "light");
  assert.equal(root.dataset["mode"], "light"); assert.equal(root.dataset["theme"], "rose"); assert.equal(root.dataset["uiContrast"], "high");
  assert.equal(root.dataset["uiText"], "large"); assert.equal(root.properties["--ink"], palette("rose", "light", 125).ink); assert.equal(root.properties["--glass"], "0.6");
  assert.equal(resolveMode("light", true), "light"); assert.equal(resolveMode("dark", false), "dark"); assert.equal(resolveMode("system", true), "dark");
});

test("the interface stylesheets carry no raw colors outside the document views", () => {
  const documentFiles = ["sheet-light.css", "reference-document.css", "template-sheet.css", "remarks.css", "export.css", "themes.css"];
  const files = ["../../../design/future-editor/visual/interface.css", "../../../design/future-editor/visual/chat.css",
    ...["aliases", "accessibility", "readability", "history", "editor-adapter", "assistant-proposals", "import-progress", "polish", "operation-feedback",
      "comparison-workspace", "original-source", "panel-handles", "assistant-commands", "templates", "settings", "frame", "utilities"].map(name => `../src/workbench/styles/${name}.css`)];
  for (const file of files) {
    assert.ok(!documentFiles.some(name => file.endsWith(name)));
    assert.deepEqual(here(file).match(/#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/g) ?? [], [], file);
  }
  const tokens = parseTokens(here("../../../design/future-editor/visual/tokens.css"));
  for (const token of colorTokens) assert.ok(tokens[token], `tokens.css defines --${token}`);
});
