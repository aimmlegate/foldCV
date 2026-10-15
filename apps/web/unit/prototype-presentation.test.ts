import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { unzipSync, strFromU8 } from "fflate";
import { Schema } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { history, undoDepth } from "@tiptap/pm/history";
import { DecorationSet } from "@tiptap/pm/view";
import Ajv2020 from "ajv/dist/2020.js";
import schema from "../../../contracts/json-schema/workspace_v6.schema.json" with { type: "json" };
import type { WorkspaceV6 } from "../src/contracts/generated/workspace_v6";
import { prototypeClass, type ViewBlock } from "../src/workbench/editor/classes";
import { prototypePresentation } from "../src/workbench/editor/presentation";
import { restoreEmptyRegions } from "../src/workbench/editor/regions";

const workspace = new Ajv2020({ strict: false }).compile<WorkspaceV6>(schema);
function fixture(name: string): WorkspaceV6 {
  const files = unzipSync(fs.readFileSync(new URL(`../../../docs/gui/handoffs/PROTOTYPE-ADOPTION/fixtures/${name}.foldcv`, import.meta.url)));
  const raw = files["workspace.json"]; assert.ok(raw);
  const value: unknown = JSON.parse(strFromU8(raw)); assert.ok(workspace(value)); return value;
}
const saved = fixture("structured"); assert.ok(saved.project);
const facts = saved.project.facts;
const paragraph: ViewBlock = { type: "paragraph", region: "main", level: null, presentation: null, empty: false, focus: false, bindings: [] };

test("period captions follow typed bindings with an intervening role paragraph", () => {
  const job = facts.records.find(record => record.kind === "employment"); assert.ok(job?.kind === "employment");
  const period = job.periods[0]; assert.ok(period);
  assert.equal(prototypeClass({ ...paragraph, bindings: [{ recordId: job.id, fieldKey: "role" }] }, facts), "cv-block");
  assert.equal(prototypeClass({ ...paragraph, bindings: [{ recordId: job.id, fieldKey: `period:${period.id}:start` },
    { recordId: job.id, fieldKey: `period:${period.id}:present` }] }, facts), "cv-block cv-caption");
  assert.equal(prototypeClass({ ...paragraph, bindings: [{ recordId: "absent", fieldKey: `period:${period.id}:start` }] }, facts), "cv-block");
});

test("focus and job technologies use real record scope, while unbound import stays prose", () => {
  const global = facts.records.find(record => record.kind === "technology" && record.jobId === null);
  const scoped = facts.records.find(record => record.kind === "technology" && record.jobId !== null);
  assert.ok(global && scoped);
  assert.equal(prototypeClass({ ...paragraph, region: "sidebar", focus: true, bindings: [{ recordId: global.id, fieldKey: "display" }] }, facts), "cv-block cv-focus");
  assert.equal(prototypeClass({ ...paragraph, bindings: [{ recordId: scoped.id, fieldKey: "display" }] }, facts), "cv-block cv-tech");
  const imported = fixture("fresh-import"); assert.ok(imported.project);
  assert.equal(imported.project.document.regions[0]?.blocks.length, 0);
  assert.equal(imported.project.document.regions[1]?.blocks.length, 0);
  assert.equal(prototypeClass(paragraph, imported.project.facts), "cv-block");
});

test("view decorations preserve document, marks and undo depth when refreshed", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
    blockContainer: { content: "(region|section|paragraph) blockGroup?", attrs: { id: { default: "" } } },
    region: { attrs: { role: { default: "main" } } },
    section: { content: "inline*", attrs: { presentation: { default: "standard" } } },
    paragraph: { content: "inline*" }, text: { group: "inline" },
    factField: { inline: true, group: "inline", content: "text*", attrs: { recordId: { default: "" }, fieldKey: { default: "" } } },
  }, marks: { bold: {} } });
  const doc = schema.node("doc", null, schema.node("blockGroup", null, schema.node("blockContainer", { id: "arbitrary-region" }, [
    schema.node("region", { role: "main" }), schema.node("blockGroup", null, schema.node("blockContainer", { id: "arbitrary-block" },
      schema.node("paragraph", null, schema.text("Retain this wording.", [schema.mark("bold")]))))])));
  const plugin = prototypePresentation(() => facts);
  let state = EditorState.create({ doc, plugins: [history(), plugin] });
  const before: unknown = state.doc.toJSON();
  const decorations = plugin.props.decorations?.call(plugin, state);
  assert.ok(decorations instanceof DecorationSet);
  assert.ok(decorations.find().length > 0);
  state = state.apply(state.tr.setMeta("foldcv-presentation", true));
  assert.deepEqual(state.doc.toJSON(), before);
  assert.equal(undoDepth(state), 0);
});

test("restoring an empty region removes only its generated placeholder and retains other regions", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
    blockContainer: { content: "(region|paragraph) blockGroup?", attrs: { id: { default: "" } } },
    region: {}, paragraph: { content: "text*" }, text: {},
  } });
  const empty = (id: string) => schema.node("blockContainer", { id }, schema.node("paragraph"));
  const roots = ["header", "sidebar", "main"].map(id => schema.node("blockContainer", { id }, [schema.node("region"),
    schema.node("blockGroup", null, empty(`${id}-placeholder`))]));
  const state = EditorState.create({ doc: schema.node("doc", null, schema.node("blockGroup", null, roots)) });
  const transaction = state.tr; restoreEmptyRegions(transaction, new Set(["header", "sidebar"]));
  const restored = state.apply(transaction);
  assert.equal(restored.doc.firstChild?.childCount, 3);
  assert.equal(restored.doc.firstChild?.child(0).childCount, 1);
  assert.equal(restored.doc.firstChild?.child(1).childCount, 1);
  assert.equal(restored.doc.firstChild?.child(2).childCount, 2);
  assert.equal(state.doc.firstChild?.child(0).childCount, 2);
  const authored = schema.node("blockContainer", { id: "header" }, [schema.node("region"), schema.node("blockGroup", null,
    schema.node("blockContainer", { id: "authored" }, schema.node("paragraph", null, schema.text("Keep this text"))))]);
  const guarded = EditorState.create({ doc: schema.node("doc", null, schema.node("blockGroup", null, authored)) });
  assert.throws(() => restoreEmptyRegions(guarded.tr, new Set(["header"])), /authored content/);
});
