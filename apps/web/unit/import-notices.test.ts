import assert from "node:assert/strict";
import test from "node:test";
import { blockNotices } from "../src/rich/import-notices";
import { literalRuns } from "../src/rich/v7-presentation";

const issue = (id: string, state: string, message: string, blockIds: string[]) => ({ id, state, message, blockIds });

test("one active remark per block; empty, retired and duplicate targets are dropped", () => {
  assert.deepEqual(blockNotices([]), []);
  assert.deepEqual(blockNotices([
    issue("blank", "active", "   ", ["a"]),
    issue("retired", "retired", "Старое", ["a"]),
    issue("none", "active", "Нет блока", []),
    issue("empty-id", "active", "Пустой адрес", [""]),
    issue("first", "active", " Первая ", ["a", "b"]),
    issue("second", "active", "Вторая", ["a", "b"]),
    issue("third", "active", "Третья", ["c"]),
    issue("fourth", "active", "Повтор", ["a"]),
    issue("retired-state", "retired", "Скрыто", ["c"]),
  ]), [
    { id: "first", blockId: "a", message: "Первая" },
    { id: "second", blockId: "b", message: "Вторая" },
    { id: "third", blockId: "c", message: "Третья" },
  ]);
});

test("literal style ranges ignore field keys and reversed bounds", () => {
  assert.deepEqual(literalRuns(undefined), []);
  assert.deepEqual(literalRuns({ "binding-1": "emphasis", "literal@0@4": "emphasis", "literal@4@4": "emphasis",
    "literal@x@2": "emphasis", "literal@8@6": "caption", "literal@2@3": "" }), [{ start: 0, end: 4, style: "emphasis" }]);
  assert.deepEqual(literalRuns({ "literal@10@12": "caption", "literal@1@2": "emphasis" }),
    [{ start: 1, end: 2, style: "emphasis" }, { start: 10, end: 12, style: "caption" }]);
});
