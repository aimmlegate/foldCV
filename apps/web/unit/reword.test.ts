import assert from "node:assert/strict";
import test from "node:test";
import { ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { REWORD_MODES, instructionFor, kindLabel, refusalLabel, writeNote, type RewordPreview, type RewordValue } from "../src/workbench/editor/reword";

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
  assert.deepEqual(await connection.rewordBlocks(), { rules: { "block-1": "Задачи: одна зона ответственности." }, write: [] });
  assert.deepEqual(await connection.sourceDiff(), { added: { cell: ["лет"] }, removed: [{ text: "Java — около 5 лет", words: ["около"] }] });
  // The request the user saw is all that is sent about style.
  const preview = await connection.rewordPreview("request-1", "block-1", "Сократи");
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", requestId: "request-1", blockId: "block-1", instruction: "Сократи" });
  // «Написать заново по резюме» names its action; the reword sends none, as before.
  await connection.rewordPreview("request-2", "block-1", "Коротко.", "write");
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", requestId: "request-2", blockId: "block-1", instruction: "Коротко.", mode: "write" });
  const result: EditResult = await connection.rewordApply("mutation-1", "block-1", [{ recordId: "record-1", field: "value", value: "Стало", edited: false }], preview.touched);
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", clientMutationId: "mutation-1", blockId: "block-1",
    changes: [{ recordId: "record-1", field: "value", value: "Стало", edited: false }], touched: { "record-1": "hash" } });
  assert.deepEqual(result.changedBlockIds, ["block-1"]);
  assert.equal(connection.response.workspace.projectRevision, 7);
});

test("«Написать заново по резюме»: the two actions each say what they do, a switch puts the block's rules in an empty field", () => {
  assert.deepEqual(REWORD_MODES.map(item => [item.mode, item.label]), [["reword", "Изменить формулировку"], ["write", "Написать заново по резюме"]]);
  assert.ok(REWORD_MODES.every(item => item.line.endsWith(".")));
  const presets = ["Сократи.", "Сделай яснее."];
  assert.equal(instructionFor("write", "", "О себе: 2–3 предложения.", presets), "О себе: 2–3 предложения.");
  assert.equal(instructionFor("write", "Сократи.", "О себе: 2–3 предложения.", presets), "О себе: 2–3 предложения.");
  // The user's own words stay, and a switch back changes nothing.
  assert.equal(instructionFor("write", "Про биллинг.", "О себе: 2–3 предложения.", presets), "Про биллинг.");
  assert.equal(instructionFor("reword", "О себе: 2–3 предложения.", "О себе: 2–3 предложения.", presets), "О себе: 2–3 предложения.");
});

test("a written text that code refused is named against the CV; a reply with no text or the same text has its own note", () => {
  assert.equal(refusalLabel(value("number", ["12"]), "write"), "появилось число, которого нет в резюме: 12");
  assert.equal(refusalLabel(value("name", ["senior"]), "write"), "появилось название, которого нет в резюме: senior");
  assert.equal(refusalLabel(value("lines", []), "write"), "текст не назвал ни одной строки резюме");
  assert.equal(refusalLabel(value("language", []), "write"), "текст написан не на языке резюме");
  assert.equal(refusalLabel(value("number", ["12"])), "появилось число, которого нет в тексте и в оригинале: 12");
  const preview = (state: RewordValue["state"], reason: string | null, after: string | null): RewordPreview => ({ requestId: "r", blockId: "b",
    touched: {}, mode: "write", values: [{ ...value(reason, []), state, after }] });
  assert.equal(writeNote(preview("refused", "empty", null)), "Модель не написала текст. Измените запрос и попробуйте ещё раз.");
  assert.equal(writeNote(preview("same", null, null)), "Модель вернула прежний текст.");
  assert.equal(writeNote(preview("refused", "name", "Текст")), null);
  assert.equal(writeNote(preview("changed", null, "Текст")), null);
});
