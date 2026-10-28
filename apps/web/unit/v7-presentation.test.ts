import assert from "node:assert/strict";
import test from "node:test";
import { literalRuns, sheetColumns } from "../src/rich/v7-presentation";

test("literal style ranges ignore field keys and reversed bounds", () => {
  assert.deepEqual(literalRuns(undefined), []);
  assert.deepEqual(literalRuns({ "binding-1": "emphasis", "literal@0@4": "emphasis", "literal@4@4": "emphasis",
    "literal@x@2": "emphasis", "literal@8@6": "caption", "literal@2@3": "" }), [{ start: 0, end: 4, style: "emphasis" }]);
  assert.deepEqual(literalRuns({ "literal@10@12": "caption", "literal@1@2": "emphasis" }),
    [{ start: 1, end: 2, style: "emphasis" }, { start: 10, end: 12, style: "caption" }]);
});

test("a layout without a sidebar is one column that stacks the regions and hides the empty sidebar button", () => {
  const header = { id: "header", x: 20, width: 556, flow: "first_page_header" } as const;
  const sidebar = { id: "sidebar", x: 20, width: 130, flow: "independent_column" } as const;
  const main = { id: "main", x: 160, width: 420, flow: "independent_column" } as const;
  assert.deepEqual(sheetColumns([header, sidebar, main]), { "--fcv-left": "20pt", "--fcv-header-left": "0pt", "--fcv-header-width": "556pt",
    "--fcv-columns": "130pt 420pt", "--fcv-gap": "10pt", "--fcv-main-column": "2", "--fcv-main-row": "2", "--fcv-sidebar-empty": "block" });
  assert.deepEqual(sheetColumns([{ ...header, x: 40 }, { ...main, x: 34, width: 528 }]), { "--fcv-left": "34pt", "--fcv-header-left": "6pt",
    "--fcv-header-width": "556pt", "--fcv-columns": "528pt", "--fcv-gap": "0pt", "--fcv-main-column": "1", "--fcv-main-row": "3",
    "--fcv-sidebar-empty": "none" });
  assert.equal(sheetColumns([header, sidebar]), null, "a layout needs its main column");
});
