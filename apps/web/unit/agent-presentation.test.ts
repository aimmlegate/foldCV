import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { drawerSize, sourceUrl, submitKey } from "../src/assistant/presentation";
import { MessageText } from "../src/assistant/MessageText";

test("assistant message markup stays plain text and stored source URLs reject active schemes", () => {
  const html = renderToStaticMarkup(createElement(MessageText, { text: '<img src="https://unretrieved.example/pixel"> [link](https://unretrieved.example) https://unretrieved.example', truncated: false, error: null }));
  assert.equal(/<img|<a\s/.test(html), false); assert.ok(html.includes("&lt;img"));
  for (const value of ["javascript:alert(1)", "data:text/html,test", "https://user:secret@example.com", "invalid"]) assert.equal(sourceUrl(value), null);
  assert.equal(sourceUrl("https://example.com/vacancy"), "https://example.com/vacancy");
});

test("assistant drawer persistence contains only bounded dimensions and collapse state", () => {
  assert.deepEqual(drawerSize(null), { collapsed: true, height: 320 });
  assert.deepEqual(drawerSize({ height: 10000, collapsed: false, token: "do-not-store", messages: ["private"] }), { height: 520, collapsed: false });
  assert.deepEqual(drawerSize({ height: NaN, collapsed: "bad" }), { height: 320, collapsed: true });
});

test("assistant Enter sends only outside composition and Shift retains a newline", () => {
  assert.ok(submitKey("Enter", false, false, false, 13));
  assert.equal(submitKey("Enter", true, false, false, 13), false);
  assert.equal(submitKey("Enter", false, true, false, 13), false);
  assert.equal(submitKey("Enter", false, false, true, 13), false);
  assert.equal(submitKey("Enter", false, false, false, 229), false);
  assert.equal(submitKey("a", false, false, false, 65), false);
});
