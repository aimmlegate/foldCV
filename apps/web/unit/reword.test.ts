import assert from "node:assert/strict";
import test from "node:test";
import { ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { kindLabel, refusalLabel, type RewordValue } from "../src/workbench/editor/reword";

const value = (reason: string | null, words: string[]): RewordValue => ({ id: "V1", recordId: "record-1", field: "value", kind: "tasks",
  before: "Было", after: "Стало", state: "refused", reason, words, source: [] });

test("a value's kind and a refusal are named in words; an unknown kind shows as the template names it", () => {
  assert.equal(kindLabel("tasks"), "Задача");
  assert.equal(kindLabel("project.description"), "Описание проекта");
  assert.equal(kindLabel("custom.field"), "custom.field");
  assert.equal(refusalLabel(value("number", ["14"])), "появилось число, которого нет в тексте и в оригинале: 14");
  assert.equal(refusalLabel(value("long", [])), "текст стал слишком длинным");
  assert.equal(refusalLabel(value("other", [])), "текст не прошёл проверку");
});

test("the preview and the Apply of a reworded block go with this page's token, and the Apply's result becomes the shown state", async () => {
  const sent: { path: string; body: Record<string, unknown> }[] = [];
  const response = { workspace: { projectId: "p", projectRevision: 7 } }, history = { undo: null, redo: null };
  const fetcher: Fetcher = (input, init) => {
    const body = typeof init.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {};
    sent.push({ path: input, body });
    const reply = input.endsWith("/reword/blocks") ? { blockIds: ["block-1"], rules: { "block-1": "Задачи: одна зона ответственности." } }
      : input.endsWith("/source-diff") ? { added: { cell: ["лет"] }, removed: [{ text: "Java — около 5 лет", words: ["около"] }] }
      : input.endsWith("/reword/preview") ? { requestId: body["requestId"], blockId: body["blockId"], values: [], touched: { "record-1": "hash" } }
      : { response, history, changedBlockIds: ["block-1"] };
    return Promise.resolve(new Response(JSON.stringify(reply), { status: 200 }));
  };
  const connection = new ProjectEditorConnection("p", "token-1", { workspace: { projectId: "p", projectRevision: 6 } } as never, history, fetcher);
  // Each block comes with the rules the panel offers as a request.
  assert.deepEqual(await connection.rewordBlocks(), { "block-1": "Задачи: одна зона ответственности." });
  assert.deepEqual(await connection.sourceDiff(), { added: { cell: ["лет"] }, removed: [{ text: "Java — около 5 лет", words: ["около"] }] });
  // The request the user saw is all that is sent about style.
  const preview = await connection.rewordPreview("request-1", "block-1", "Сократи");
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", requestId: "request-1", blockId: "block-1", instruction: "Сократи" });
  const result: EditResult = await connection.rewordApply("mutation-1", "block-1", [{ recordId: "record-1", field: "value", value: "Стало" }], preview.touched);
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", clientMutationId: "mutation-1", blockId: "block-1",
    changes: [{ recordId: "record-1", field: "value", value: "Стало" }], touched: { "record-1": "hash" } });
  assert.deepEqual(result.changedBlockIds, ["block-1"]);
  assert.equal(connection.response.workspace.projectRevision, 7);
});
