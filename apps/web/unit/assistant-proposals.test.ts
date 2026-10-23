import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProposalPreview, proposalControls } from "../src/assistant/proposal";
import { validateContract } from "../src/contracts/validate";
import { proposal } from "./support/assistant-proposal";
import { taskCatalog } from "./support/assistant-capabilities";

test("preview renders exact server comparison as plain text and native keyboard controls without a modal", () => {
  const value = proposal(); value.changes[0]!.after = '<img src="https://example.invalid/tracker"> Создавал 😀';
  const html = renderToStaticMarkup(createElement(ProposalPreview, { value, catalog: taskCatalog(), busy: false,
    invalidated: false, allowEdits: false, apply: () => {}, discard: () => {} }));
  assert.ok(html.includes("Разрабатывал API 😀") && html.includes("&lt;img"));
  assert.equal(/<img|<dialog|role="dialog"/.test(html), false);
  assert.ok(html.includes("<summary>") && html.includes('type="button"') && html.includes("Применить"));
  assert.ok(html.includes("Документ пока не изменён"));
});

test("explicit controls follow server stages and stay disabled while stale, busy, read-only or unknown", () => {
  const value = proposal(), catalog = taskCatalog();
  assert.ok(catalog.tasks[0]); catalog.tasks[0].apply = { state: "available", reason: null, reasonCode: null, remedy: null };
  assert.ok(proposalControls(value, catalog, false, false, true).apply);
  for (const state of ["building", "incomplete", "stale", "cancelled", "outcome_unknown", "applied"] as const)
    assert.equal(proposalControls({ ...value, state }, catalog, false, false, true).apply, false);
  assert.equal(proposalControls(value, catalog, true, false, true).apply, false);
  assert.equal(proposalControls(value, catalog, false, true, true).apply, false);
  assert.equal(proposalControls(value, catalog, false, false, false).apply, false);
  const failed = { ...value, state: "failed_before_commit" as const };
  assert.equal(proposalControls(failed, catalog, false, false, true).apply, false);
  assert.ok(proposalControls(failed, catalog, false, false, true, catalog.tasks[0].apply).apply);
  const html = renderToStaticMarkup(createElement(ProposalPreview, { value: { ...value, state: "outcome_unknown" }, catalog,
    busy: false, invalidated: false, allowEdits: true, apply: () => {}, discard: () => {} }));
  assert.equal(html.includes("Документ пока не изменён"), false);
  assert.ok(html.includes("Проверяем исходное сохранение"));
  const saved = renderToStaticMarkup(createElement(ProposalPreview, { value: { ...value, state: "applied" }, catalog,
    busy: false, invalidated: true, allowEdits: true, apply: () => {}, discard: () => {} }));
  assert.ok(saved.includes("Вариант сохранён"));
  assert.equal(saved.includes("Подготовьте новый вариант; текущие правки сохранены"), false);
});

test("acceptance wire requires protocol, exact content identity and UI-only owner; model booleans cannot approve", () => {
  const value = { protocolVersion: 1, proposalId: "proposal_1", version: 1, contentSha256: "b".repeat(64),
    owner: { epoch: 1, token: "synthetic_owner_capability_0123456789" } };
  assert.ok(validateContract("assistant_proposal_accept_v1", value));
  assert.equal(validateContract("assistant_proposal_accept_v1", { ...value, approved: true }), false);
  assert.equal(validateContract("assistant_proposal_accept_v1", { ...value, owner: null }), false);
  assert.equal(validateContract("assistant_proposal_accept_v1", { ...value, protocolVersion: undefined }), false);
});

test("action preview displays the server's exact target and irreversible consequence without promising editor Undo", () => {
  const value = proposal(), catalog = taskCatalog();
  value.taskId = "delete_project"; value.reason = "Удалить проект «Синтетический проект». Локальные файлы будут удалены окончательно; отмены в редакторе нет.";
  assert.ok(catalog.tasks[0]); Object.assign(catalog.tasks[0], { id: "delete_project", effect: "project_action", reversibility: "action_specific" });
  const html = renderToStaticMarkup(createElement(ProposalPreview, { value, catalog, busy: false,
    invalidated: false, allowEdits: true, apply: () => {}, discard: () => {} }));
  assert.ok(html.includes("Синтетический проект") && html.includes("удалены окончательно"));
  assert.equal(html.includes("одна отмена в истории"), false);
});
