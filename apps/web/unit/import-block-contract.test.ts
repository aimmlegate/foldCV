import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../contracts/examples/background/background_writer_bridge.json" with { type: "json" };
import { backgroundReply } from "../src/background/api";
import { validateRichWorkspaceShape } from "../src/rich/validate";

async function draftWorkspace() {
  const view = await backgroundReply("background_writer_view_v1", fixture.before);
  const workspace = structuredClone(view.response.workspace);
  const project = workspace.project;
  assert.ok(project);
  workspace.project = null;
  workspace.preDraft = {
    selectedInput: "file", selectedSourceId: project.sources[0]?.id ?? null,
    sources: project.sources, facts: project.facts, operations: [], warnings: [],
    importDraft: {
      version: 1, sourceSha256: "a".repeat(64), skillSha256: "b".repeat(64), runId: "import-test",
      sequence: 1, facts: [], receipts: [], finished: false, issues: [],
      profile: { name: "Candidate", title: "Engineer", location: "", sourceKeys: [] },
      blocks: [
        { id: "visible", kind: "heading", sourceKeys: ["part_1", "part_2"], modelBlock: true },
        { id: "repeat", kind: "duplicate", sourceKeys: ["part_3"], duplicateOf: ["part_1", "part_2"], modelBlock: true },
      ],
    },
  };
  return workspace;
}

test("import progress accepts persisted semantic blocks and duplicate source links", async () => {
  const workspace = await draftWorkspace();
  assert.ok(validateRichWorkspaceShape(workspace));
  const blocks = workspace.preDraft?.importDraft?.blocks;
  assert.equal(blocks?.[0]?.kind, "heading");
  assert.deepEqual(blocks?.[1]?.duplicateOf, ["part_1", "part_2"]);
});

test("import draft shape rejects unknown block kinds and malformed duplicate links", async () => {
  const workspace = await draftWorkspace();
  for (const [key, value] of [["kind", "unknown"], ["modelBlock", "yes"], ["duplicateOf", [42]]] as const) {
    const invalid = structuredClone(workspace);
    const block = invalid.preDraft?.importDraft?.blocks?.[1];
    assert.ok(block);
    Reflect.set(block, key, value);
    assert.equal(validateRichWorkspaceShape(invalid), false);
  }
});

test("import progress accepts edited text with its captured permission and source keys", async () => {
  const workspace = await draftWorkspace();
  const draft = workspace.preDraft?.importDraft;
  assert.ok(draft);
  draft.allowTextRewrite = true;
  const block = draft.blocks?.[0];
  assert.ok(block);
  block.text = "A clearer source-backed heading";
  assert.ok(validateRichWorkspaceShape(workspace));
  for (const [key, value] of [["allowTextRewrite", "false"], ["text", 42]] as const) {
    const invalid = structuredClone(workspace);
    const target = key === "allowTextRewrite" ? invalid.preDraft?.importDraft : invalid.preDraft?.importDraft?.blocks?.[0];
    assert.ok(target);
    Reflect.set(target, key, value);
    assert.equal(validateRichWorkspaceShape(invalid), false);
  }
});
