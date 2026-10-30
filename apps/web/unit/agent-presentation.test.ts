import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { lostLink } from "../src/assistant/controller";
import { drawerSize, rereadsCapabilities, sourceUrl, stopBusy, submitKey } from "../src/assistant/presentation";
import { MessageText } from "../src/assistant/MessageText";
import { capabilities, run, settings, view } from "./support/assistant";

test("assistant message markup stays plain text and stored source URLs reject active schemes", () => {
  const html = renderToStaticMarkup(createElement(MessageText, { text: '<img src="https://unretrieved.example/pixel"> [link](https://unretrieved.example) https://unretrieved.example', truncated: false, error: null }));
  assert.equal(/<img|<a\s/.test(html), false); assert.ok(html.includes("&lt;img"));
  for (const value of ["javascript:alert(1)", "data:text/html,test", "https://user:secret@example.com", "invalid"]) assert.equal(sourceUrl(value), null);
  assert.equal(sourceUrl("https://example.com/vacancy"), "https://example.com/vacancy");
});

test("Stop stays usable for a cancelling run whose follow loop gave up", () => {
  assert.equal(stopBusy(view({ run: run("cancelling") })), true);
  assert.equal(stopBusy(view({ run: run("cancelling"), loading: lostLink })), false);
  assert.equal(stopBusy(view({ run: run("running"), loading: "Останавливаем" })), true);
  assert.equal(stopBusy(view({ run: run("running") })), false);
});

test("every refusal on an enabled panel is re-read, not only the connection one", () => {
  for (const code of ["AGENT_CONNECTION_UNAVAILABLE", "AGENT_MODEL_UNAVAILABLE", "AGENT_AUTH_REQUIRED"])
    assert.equal(rereadsCapabilities(view({ settings, capabilities: { ...capabilities, ready: false, unavailable: { code, detail: [] } } })), true, code);
  assert.equal(rereadsCapabilities(view({ settings, capabilities })), false);
  assert.equal(rereadsCapabilities(view({ settings: { ...settings, enabled: false }, capabilities: { ...capabilities, ready: false, unavailable: { code: "AGENT_DISABLED", detail: [] } } })), false);
  assert.equal(rereadsCapabilities(null), false);
});

test("assistant drawer persistence contains only bounded dimensions and collapse state", () => {
  assert.deepEqual(drawerSize(null), { collapsed: true, height: 320 });
  assert.deepEqual(drawerSize({ height: 10000, collapsed: false, token: "do-not-store", messages: ["private"] }), { height: 720, collapsed: false });
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
