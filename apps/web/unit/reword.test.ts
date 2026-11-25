import assert from "node:assert/strict";
import test from "node:test";
import { ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { REWORD_MODES, instructionFor, kindLabel, listApply, listDraft, listNote, refusalLabel, writeNote, type RewordPreview, type RewordValue } from "../src/workbench/editor/reword";

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
  // A list's Apply sends the items that go and come.
  await connection.rewordApply("mutation-0", "block-1", [], { "block-1": "h" }, { removed: ["record-1"], added: [{ text: "Новый", lines: ["S2"], edited: false }] });
  assert.deepEqual(sent.at(-1)?.body, { editorToken: "token-1", clientMutationId: "mutation-0", blockId: "block-1", changes: [],
    touched: { "block-1": "h" }, removed: ["record-1"], added: [{ text: "Новый", lines: ["S2"], edited: false }] });
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

test("a list written again (F6b): «оставить» starts on for the user's own item, the Apply names what goes and what comes", () => {
  const present = (id: string, keep = false): RewordValue => ({ id, recordId: "record-" + id, field: "text", kind: "items", before: "Было " + id,
    after: null, state: "present", reason: null, words: [], source: [], ...(keep ? { keep } : {}) });
  const item = (id: string, state: "added" | "refused" = "added") => ({ id, text: "Новый " + id, lines: ["S2"], source: [], state, reason: null, words: [] });
  const preview: RewordPreview = { requestId: "r", blockId: "list", touched: {}, mode: "write", shape: "items",
    values: [present("P1"), present("P2", true), present("P3")], added: [item("N1"), item("N2"), item("N3", "refused")] };
  const draft = listDraft(preview);
  assert.deepEqual([...draft.keep], ["record-P2"]);
  assert.deepEqual(listApply(preview, draft), { removed: ["record-P1", "record-P3"], ready: true,
    added: [{ text: "Новый N1", lines: ["S2"], edited: false }, { text: "Новый N2", lines: ["S2"], edited: false }] });
  // An unticked new item does not come; an edited one is the user's.
  const changed = { ...draft, skipped: new Set(["N2"]), texts: { N1: "Новый N1 сама" } };
  assert.deepEqual(listApply(preview, changed).added, [{ text: "Новый N1 сама", lines: ["S2"], edited: true }]);
  // Nothing changes, or the list would be empty: no Apply.
  assert.equal(listApply(preview, { ...draft, keep: new Set(["record-P1", "record-P2", "record-P3"]), skipped: new Set(["N1", "N2"]) }).ready, false);
  assert.equal(listApply(preview, { ...draft, keep: new Set(), skipped: new Set(["N1", "N2"]) }).ready, false);
  assert.equal(listNote(preview), null);
  assert.equal(listNote({ ...preview, added: [] }), "Модель не написала пунктов. Измените запрос и попробуйте ещё раз.");
  assert.equal(listNote({ ...preview, added: [item("N1", "refused")] }), "Ни один пункт не прошёл проверку.");
  assert.equal(refusalLabel({ reason: "duplicate", words: [] }, "write"), "такой пункт уже есть");
});
