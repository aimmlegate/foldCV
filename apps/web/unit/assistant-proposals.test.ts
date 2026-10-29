import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProposalPreview, proposalControls, proposalTitle } from "../src/assistant/proposal";
import { proposal } from "./support/assistant";

const render = (props: Partial<Parameters<typeof ProposalPreview>[0]>) => renderToStaticMarkup(createElement(ProposalPreview, {
  value: proposal(), busy: false, applying: false, stale: false, allowEdits: true, apply: () => {}, discard: () => {}, ...props }));

test("the preview shows the server's before and after text as plain text, with native controls and no modal", () => {
  const value = proposal({ preview: [{ target: "block-paper-a", label: "set_block_text", before: "Разработал API 😀",
    after: '<img src="https://example.invalid/tracker"> Создавал 😀' }] });
  const html = render({ value });
  assert.ok(html.includes("Разработал API 😀") && html.includes("&lt;img"));
  assert.equal(/<img|<dialog|role="dialog"/u.test(html), false);
  assert.ok(html.includes("Было") && html.includes("Станет") && html.includes("Текст · 1"));
  assert.ok(html.includes("одним шагом"));
});

test("Apply needs a current draft and the edits flag; Discard needs only a draft", () => {
  const value = proposal();
  assert.deepEqual(proposalControls(value, false, false, true), { apply: true, discard: true, reason: null });
  assert.equal(proposalControls(value, true, false, true).apply, false);
  const off = proposalControls(value, false, false, false);
  assert.equal(off.apply, false); assert.equal(off.discard, true); assert.match(off.reason ?? "", /«Разрешить правки»/u);
  const stale = proposalControls(value, false, true, true);
  assert.equal(stale.apply, false); assert.match(stale.reason ?? "", /Документ изменился/u);
  for (const state of ["applied", "discarded"] as const) assert.deepEqual(proposalControls({ ...value, state }, false, false, true), { apply: false, discard: false, reason: null });
  assert.ok(render({ stale: true }).includes("Правки устарели"));
  assert.ok(render({ value: { ...value, state: "applied" } }).includes("Правки применены"));
});

test("Apply shows its own progress; a decided proposal shows its outcome, not dead buttons", () => {
  const value = proposal();
  const applying = render({ busy: true, applying: true });
  assert.ok(applying.includes("Применяем…") && applying.includes('aria-busy="true"'));
  assert.equal(render({ busy: true }).includes("Применяем…"), false);
  const applied = render({ value: { ...value, state: "applied" } });
  assert.ok(applied.includes('data-state="applied"') && applied.includes("внесены в резюме"));
  for (const html of [applied, render({ value: { ...value, state: "discarded" } })]) {
    assert.equal(/>Применить<|>Отклонить<|одним шагом/u.test(html), false);
  }
  assert.ok(render({ stale: true }).includes(">Применить<"));
});

test("history and project actions name what Apply does", () => {
  assert.equal(proposalTitle(proposal({ kind: "history", ops: [{ op: "history", direction: "undo" }] })), "Отменить последнее действие");
  assert.equal(proposalTitle(proposal({ kind: "action", ops: [{ op: "action", action: "archive", value: null, targetId: null }] })), "Перенести резюме в архив");
  const html = render({ value: proposal({ kind: "history", ops: [{ op: "history", direction: "redo" }], preview: [] }) });
  assert.ok(html.includes("Повторить отменённое действие") && !html.includes("одним шагом"));
});
