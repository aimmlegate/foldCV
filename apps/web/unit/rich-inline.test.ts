import assert from "node:assert/strict";
import test from "node:test";
import { fromInline, toInline, wireColor, type EditorInline } from "../src/rich/inline";

test("partially styled fact text keeps every mark and stable identity through rich round trips", () => {
  const input: EditorInline[] = [{ type: "factField", props: { bindingId: "name-binding", recordId: "candidate", fieldKey: "name", syncedFactRevision: 4 },
    content: [{ type: "text", text: "Alex ", styles: {} }, { type: "text", text: "Example", styles: { bold: true, italic: true, textColor: "red" } }] }];
  const ids = new Map<string, string>();
  const allocate = (base: string, key: string) => { const id = ids.get(base + key) ?? `fragment-${ids.size}`; ids.set(base + key, id); return id; };
  const result = fromInline(input, allocate);
  assert.equal(result.length, 2);
  const first = result[0], second = result[1];
  assert.ok(first?.type === "fact_field" && second?.type === "fact_field");
  assert.equal(first.bindingId, "name-binding"); assert.notEqual(first.bindingId, second.bindingId);
  assert.equal(first.text + second.text, "Alex Example");
  assert.deepEqual({ bold: second.styles.bold, italic: second.styles.italic, color: second.styles.textColor }, { bold: true, italic: true, color: "#e03e3e" });
  assert.equal(second.recordId, "candidate"); assert.equal(second.syncedFactRevision, 4);
  assert.deepEqual(fromInline(input, allocate), result);
  assert.deepEqual(fromInline(toInline(result), allocate), result);
});

test("links retain exact long targets and separately styled runs with explicit RGB palette values", () => {
  const url = "https://example.com/" + "x".repeat(1500);
  const result = fromInline([{ type: "link", href: url, content: [
    { type: "text", text: "first", styles: { underline: true, backgroundColor: "blue" } },
    { type: "text", text: "second", styles: { strike: true, code: true, textColor: "rgb(12, 34, 56)" } },
  ] }], base => base);
  assert.equal(result[0]?.type, "link");
  if (result[0]?.type !== "link") throw new Error("Missing link");
  assert.equal(result[0].href, url);
  assert.equal(result[0].content[0]?.styles.backgroundColor, "#ddebf1");
  assert.equal(result[0].content[1]?.styles.textColor, "#0c2238");
  assert.equal(result[0].content[1]?.styles.strike, true);
  assert.deepEqual(fromInline(toInline(result), base => base), result);
});

test("empty fact spans keep their binding while unsupported colors cannot silently become default", () => {
  const result = fromInline([{ type: "factField", props: { bindingId: "empty", recordId: "candidate", fieldKey: "name", syncedFactRevision: 3 }, content: [] }], base => base);
  assert.ok(result[0]?.type === "fact_field");
  assert.equal(result[0].bindingId, "empty"); assert.equal(result[0].text, "");
  assert.equal(wireColor("#aBc", "text"), "#aabbcc");
  assert.throws(() => wireColor("rgb(256, 0, 0)", "text"), /RICH_COLOR_UNSUPPORTED/);
  assert.throws(() => wireColor("invented-color", "text"), /RICH_COLOR_UNSUPPORTED/);
});
