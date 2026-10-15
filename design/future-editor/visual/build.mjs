import { readFileSync, writeFileSync } from "node:fs";

const templates = JSON.parse(readFileSync(new URL("templates.json", import.meta.url), "utf8"));
const copy = JSON.parse(readFileSync(new URL("copy.ru.json", import.meta.url), "utf8"));
const parts = { shell: [readFileSync(new URL("shell.html", import.meta.url), "utf8").trim()] };
for (const [name, template] of Object.entries(templates)) {
  if (template.parts.length !== template.slots.length + 1) throw new Error(`Invalid slots: ${name}`);
  parts[name] = template.parts;
}
for (const [name, entry] of Object.entries(copy)) {
  if (entry.parts.length !== entry.slots.length + 1) throw new Error(`Invalid text slots: ${name}`);
}
const script = `"use strict";
(() => {
  const templates = ${JSON.stringify(parts, null, 2)};
  const copy = ${JSON.stringify(Object.fromEntries(Object.entries(copy).map(([name, entry]) => [name, entry.parts])), null, 2)};
  function fill(table, name, values) {
    const parts = table[name];
    if (!parts || values.length !== parts.length - 1) throw new Error("Invalid visual template: " + name);
    return parts.reduce((html, part, index) => html + (index ? String(values[index - 1]) : "") + part, "");
  }
  window.FoldCVVisual = Object.freeze({
    markup: (name, ...values) => fill(templates, name, values),
    text: (name, ...values) => fill(copy, name, values),
  });
})();
`;
writeFileSync(new URL("index.js", import.meta.url), script);
console.log(`Built ${Object.keys(parts).length} visual templates`);
