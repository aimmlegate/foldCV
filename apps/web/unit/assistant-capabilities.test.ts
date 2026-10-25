import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AgentBrowserApi } from "../src/assistant/api";
import { Capabilities } from "../src/assistant/Capabilities";
import { validateContract } from "../src/contracts/validate";
import { taskCatalog } from "./support/assistant-capabilities";

test("assistant wire validation rejects unknown versions, tasks and extra approval fields", () => {
  const value = taskCatalog();
  assert.ok(validateContract("assistant_task_catalog_v1", value));
  assert.equal(validateContract("assistant_task_catalog_v1", { ...value, protocolVersion: 2 }), false);
  assert.equal(validateContract("assistant_task_request_v1", { taskId: "shell", protocolVersion: 1 }), true);
  for (const request of [{ taskId: "invented", protocolVersion: 1 }, { taskId: "shell" },
    { taskId: "read_resume", protocolVersion: true }, { taskId: "rewrite_resume", protocolVersion: 1, approved: true }])
    assert.equal(validateContract("assistant_task_request_v1", request), false);
});

test("draft assembly carries no approval and a draft result cannot certify a save", () => {
  const request = { protocolVersion: 1, key: "call_1", taskId: "rewrite_resume", phase: "append", operations: [], snapshotIds: [], unchanged: [] };
  assert.ok(validateContract("assistant_assembly_request_v1", request));
  assert.equal(validateContract("assistant_assembly_request_v1", { ...request, approved: true }), false);
  assert.equal(validateContract("assistant_assembly_request_v1", { ...request, protocolVersion: 2 }), false);
  const result = { schemaVersion: 1, protocolVersion: 1, disposition: "draft_ready", proposalId: "proposal_1", version: 1,
    contentSha256: "a".repeat(64), changedUnits: 1, unresolvedUnits: 0, coverage: [], coverageTruncated: false, unitCount: 1,
    durable: false, reason: "Вариант готов к просмотру. Документ не изменён." };
  assert.ok(validateContract("assistant_proposal_result_v1", result));
  assert.equal(validateContract("assistant_proposal_result_v1", { ...result, durable: true }), false);
});

test("task metadata and message preflight use authenticated versioned requests without model submission", async () => {
  const requests: { path: string; body: unknown }[] = [], value = taskCatalog();
  const api = new AgentBrowserApi("project_1", (input, init) => {
    const path = String(input), headers = new Headers(init?.headers);
    assert.equal(init?.credentials, "same-origin");
    assert.equal(headers.get("X-FoldCV-Assistant-Protocol"), "1");
    requests.push({ path, body: typeof init?.body === "string" ? JSON.parse(init.body) as unknown : null });
    return Promise.resolve(Response.json(path.endsWith("check-message")
      ? { schemaVersion: 1, protocolVersion: 1, projectId: value.projectId, catalogRevision: value.catalogRevision,
        taskId: "export_pdf", availability: { state: "unsupported", reasonCode: "ASSISTANT_UNSUPPORTED_TASK", reason: "PDF недоступен.", remedy: "Экспортируйте DOCX." }, needsPlanning: false }
      : value));
  });
  await api.tasks({ allowEdits: false, allowWeb: false });
  const checked = await api.checkMessage("Экспортируй PDF", { allowEdits: false, allowWeb: false });
  assert.equal(checked.availability.state, "unsupported");
  assert.deepEqual(requests.map(request => request.path.split("/").at(-1)), ["tasks", "check-message"]);
  assert.deepEqual(requests[1]?.body, { schemaVersion: 1, protocolVersion: 1, message: "Экспортируй PDF", scope: "resume", allowEdits: false, allowWeb: false });
});

test("capability display follows server readiness and hides behind the rollout gate", () => {
  const catalog = taskCatalog(), choose = () => {};
  const html = renderToStaticMarkup(createElement(Capabilities, { catalog, busy: false, choose }));
  assert.match(html, /Что умеет помощник/);
  assert.match(html, /Правки запрещены/);
  assert.match(html, /<button/);
  assert.equal(renderToStaticMarkup(createElement(Capabilities, { catalog: { ...catalog, protocolEnabled: false }, busy: false, choose })), "");
  const denied = structuredClone(catalog);
  denied.tasks[0].generation = { state: "unsupported", reasonCode: "ASSISTANT_UNSUPPORTED_TASK", reason: "Недоступно.", remedy: "Используйте DOCX." };
  const unavailable = renderToStaticMarkup(createElement(Capabilities, { catalog: denied, busy: false, choose }));
  assert.doesNotMatch(unavailable, /<button/);
  assert.match(unavailable, /Используйте DOCX/);
});
