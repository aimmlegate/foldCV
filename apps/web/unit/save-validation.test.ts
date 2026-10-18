import assert from "node:assert/strict";
import test from "node:test";
import { performance } from "node:perf_hooks";
import Ajv2020 from "ajv/dist/2020.js";
import fixture from "../../../contracts/examples/background/background_writer_bridge.json" with { type: "json" };
import { taggedSchema } from "../src/contracts/tagged-schema";
import { backgroundReply } from "../src/background/api";
import { sha256 } from "../src/background/wire";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import type { RichDocumentV1 } from "../src/contracts/generated/rich_document_v1";

test("tagged validation visits only the matching nested branch and keeps schema rules", () => {
  const schema = { type: "object", required: ["type", "value"], discriminator: { propertyName: "type",
    mapping: { text: "#/$defs/Text", number: "#/$defs/Number" } },
  oneOf: [{ $ref: "#/$defs/Text" }, { $ref: "#/$defs/Number" }], $defs: {
    Text: { type: "object", visited: true, additionalProperties: false, properties: {
      type: { const: "text" }, value: { type: "string" }, child: { $ref: "#" } } },
    Number: { type: "object", visited: true, additionalProperties: false, properties: {
      type: { const: "number" }, value: { type: "number" }, child: { $ref: "#" } } },
  } };
  const before = JSON.stringify(schema);
  let visits = 0;
  const ajv = new Ajv2020({ strict: false, discriminator: true });
  ajv.addKeyword({ keyword: "visited", validate: () => { visits++; return true; } });
  const validate = ajv.compile(taggedSchema(schema));
  assert.ok(validate({ type: "text", value: "Keep", child: { type: "number", value: 4,
    child: { type: "text", value: "Nested" } } }));
  assert.equal(visits, 3);
  for (const value of [{ type: "text", value: 4 }, { type: "number", value: "4" },
    { type: "unknown", value: "Keep" }, { value: "Keep" }, { type: "text", value: "Keep", extra: true },
    { type: "text", value: "Keep", child: { type: "number", value: "invalid" } }]) assert.equal(validate(value), false);
  assert.equal(JSON.stringify(schema), before);
});

test("large nested save replies validate within the interaction budget", async () => {
  const view = structuredClone(await backgroundReply("background_writer_view_v1", fixture.before));
  const workspace = view.response.workspace, project = workspace.project;
  assert.ok(project);
  type Block = RichDocumentV1["regions"][number]["blocks"][number];
  const paragraph = (id: string, depth: number): Block => ({ id, type: "paragraph", revision: 1, provenance: [],
    props: { alignment: "left", textColor: "default", backgroundColor: "default" },
    content: [{ type: "text", text: "Keep this source paragraph.", styles: { bold: false, italic: false,
      underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } }],
    children: depth ? [paragraph(`${id}-child`, depth - 1)] : [] });
  project.document.regions[2].blocks = Array.from({ length: 50 }, (_, index) => paragraph(`source-${String(index)}`, 4));
  view.workspaceWire = JSON.stringify(workspace);
  view.workspaceSha256 = await sha256(view.workspaceWire);
  const started = performance.now();
  assert.ok(validateRichWorkspaceShape(workspace));
  await backgroundReply("background_writer_view_v1", view);
  assert.ok(performance.now() - started < 1000, "Nested save validation blocks the interface for over one second");
});

test("save replies still reject malformed nested values and mismatched exact bytes", async () => {
  const view = await backgroundReply("background_writer_view_v1", fixture.before);
  for (const change of ["tag", "field", "hash", "wire"] as const) {
    const invalid: unknown = structuredClone(view);
    assert.ok(typeof invalid === "object" && invalid !== null);
    if (change === "hash") Reflect.set(invalid, "workspaceSha256", "0".repeat(64));
    else if (change === "wire") {
      const wire = view.workspaceWire.replace("Styled work", "Changed work");
      Reflect.set(invalid, "workspaceWire", wire);
      Reflect.set(invalid, "workspaceSha256", await sha256(wire));
    }
    else {
      const block = structuredClone(view.response.workspace.project?.document.regions[2].blocks[0]);
      assert.ok(block);
      if (change === "tag") Reflect.set(block, "type", "unknown_block");
      else Reflect.set(block.props, "alignment", 42);
      const response = structuredClone(view.response);
      assert.ok(response.workspace.project);
      response.workspace.project.document.regions[2].blocks[0] = block;
      assert.equal(validateRichWorkspaceShape(response.workspace), false);
      Reflect.set(invalid, "response", response);
    }
    await assert.rejects(backgroundReply("background_writer_view_v1", invalid), /INVALID_RESULT/u);
  }
});
