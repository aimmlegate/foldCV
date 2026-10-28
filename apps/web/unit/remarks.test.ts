import assert from "node:assert/strict";
import test from "node:test";
import { checkCount, checkRemarks, EMPTY_BLOCK, importRemarks, LINK_WITHOUT_TARGET, placeRemarks, type OutlineDocument, type Remark }
  from "../src/rich/remarks";

type Block = OutlineDocument["regions"][number]["blocks"][number];
const text = (value: string) => [{ type: "text", text: value, styles: {} }];
const line = (id: string, value: string, children: Block[] = []): Block => ({ id, type: "paragraph", content: text(value), children });
const heading = (id: string, value: string): Block => ({ id, type: "heading", content: text(value), children: [] });
const item = (id: string, children: Block[]): Block => ({ id, type: "section", children });

// A header without a heading, a sidebar Focus list and a main column with projects and a loose fallback line.
const document: OutlineDocument = { regions: [
  { id: "header", role: "header", blocks: [item("identity", [line("name", "Alex Example"), line("title", "Backend engineer")])] },
  { id: "sidebar", role: "sidebar", blocks: [heading("focus", "ФОКУС"),
    item("focus-python", [line("python", "Python"), line("python-years", "3 years")]),
    item("focus-teamcity", [line("teamcity", "TeamCity"), line("teamcity-years", "1 year")])] },
  { id: "main", role: "main", blocks: [heading("projects", "ПРОЕКТЫ"),
    item("labs", [line("labs-title", "Example Labs — Queue Platform"), line("labs-role", "Роль: backend engineer"),
      { id: "labs-link", type: "paragraph", content: [{ type: "bound_link", href: "", content: text("Портфолио") }], children: [] }]),
    item("old", [line("old-title", "Old Systems")]), line("fallback", "Reduced median latency by 80%."),
    heading("summary", "О СЕБЕ"), line("empty", "")] },
] };
const remark = (id: string, blockIds: string[], message = `Замечание ${id}`): Remark => ({ id, source: "import", message, blockIds });

test("sections follow the document headings; a header without one is named by its region", () => {
  const placed = placeRemarks(document, []);
  assert.deepEqual(placed.sections.map(section => [section.id, section.title, section.focusId]),
    [["header", "Шапка", "name"], ["focus", "ФОКУС", "focus"], ["projects", "ПРОЕКТЫ", "projects"], ["summary", "О СЕБЕ", "summary"]]);
  assert.equal(placed.count, 0);
  assert.ok(placed.sections.every(section => section.items.length === 0 && section.remarks.length === 0), "only items with remarks are listed");
});

test("a remark on one item marks that item; on several items, a heading or two sections it marks each section heading", () => {
  const placed = placeRemarks(document, [
    remark("teamcity", ["teamcity-years"]),
    remark("role", ["labs-role", "labs"]),
    remark("two-items", ["labs-title", "old-title"]),
    remark("heading", ["focus"]),
    remark("across", ["python", "fallback"]),
    remark("loose", ["fallback"]),
    remark("gone", ["deleted-block"]),
    remark("teamcity", ["python"], "Повтор того же замечания"),
    remark("blank", ["python"], "   "),
  ]);
  const [header, focus, projects, summary] = placed.sections;
  assert.ok(header && focus && projects && summary);
  assert.deepEqual(focus.items.map(entry => [entry.blockId, entry.focusId, entry.label, entry.remarks.map(value => value.id)]),
    [["focus-teamcity", "teamcity", "TeamCity", ["teamcity"]]]);
  assert.deepEqual(focus.remarks.map(value => value.id), ["heading", "across"]);
  assert.deepEqual(projects.items.map(entry => [entry.blockId, entry.label, entry.remarks.map(value => value.id)]),
    [["labs", "Example Labs — Queue Platform", ["role"]], ["fallback", "Reduced median latency by 80%.", ["loose"]]]);
  assert.deepEqual(projects.remarks.map(value => value.id), ["two-items", "across"], "a remark spanning two sections is at both headings");
  assert.deepEqual(header.remarks, []);
  assert.deepEqual(placed.unplaced.map(value => value.id), ["gone"]);
  assert.equal(placed.count, 7, "a repeated id and a blank message are not counted");
});

test("active import issues become remarks; retired ones and empty messages do not", () => {
  assert.deepEqual(importRemarks([
    { id: "a", state: "active", message: " Проверьте роль ", blockIds: ["labs-role"] },
    { id: "b", state: "retired", message: "Старое", blockIds: ["labs-role"] },
    { id: "c", state: "active", message: "", blockIds: ["old-title"] },
  ]), [{ id: "a", source: "import", message: "Проверьте роль", blockIds: ["labs-role"] }]);
});

test("check findings are placed like import remarks and counted with the open import issues", () => {
  const result = { emptyBlocks: ["empty", "summary"], linksWithoutTarget: ["labs-link", "labs-link"], openImportIssues: [{ id: "x", blockIds: [] }] };
  const remarks = checkRemarks(result);
  assert.deepEqual(remarks.map(value => [value.id, value.message]), [["check-empty:empty", EMPTY_BLOCK], ["check-empty:summary", EMPTY_BLOCK],
    ["check-link:labs-link", LINK_WITHOUT_TARGET]]);
  assert.equal(checkCount(result), 4);
  assert.equal(checkCount({ emptyBlocks: [], linksWithoutTarget: [], openImportIssues: [] }), 0);
  const summary = placeRemarks(document, remarks).sections.find(section => section.id === "summary");
  assert.deepEqual(summary?.items.map(entry => [entry.blockId, entry.label, entry.focusId]), [["empty", "", "empty"]],
    "an empty item has no label; the panel names it «Без текста»");
  assert.deepEqual(summary?.remarks.map(value => value.id), ["check-empty:summary"], "an empty heading is a section remark");
  const projects = placeRemarks(document, remarks).sections.find(section => section.id === "projects");
  assert.deepEqual(projects?.items.map(entry => entry.blockId), ["labs"], "a link inside an item marks that item");
});
