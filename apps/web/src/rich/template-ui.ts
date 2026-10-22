import type { RichDocumentV2 } from "../contracts/generated/rich_document_v2";
import type { WorkingFactsV2 } from "../contracts/generated/working_facts_v2";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "../contracts/lossless-json";
import { templateProjectWire } from "../contracts/template-validate";
import type { CellChange, CellValue } from "./history";

type BuiltinRecord = WorkingFactsV2["records"][number];
const fields = {
  candidate: ["name", "title", "location"], detail: ["value"], employment: ["employer", "role"],
  subproject: ["name", "role"], technology: ["canonicalId", "display", "experience"],
  education: ["institution", "qualification", "specialty", "completion"], language: ["language", "level"],
  certification: ["name", "issuer", "date"], claim: ["value"], metric: ["value"], leadership: ["value"],
  unresolved: [],
} as const satisfies Record<BuiltinRecord["kind"], readonly string[]>;

export type TemplateUiProjection = {
  projectId: string;
  responseWire: string;
  packageWire: string;
  cells: ReadonlyMap<string, CellValue>;
};
export const templateBlockCell = (id: string): string => JSON.stringify(["template-block", id]);
export const templateRegionCell = (id: string): string => JSON.stringify(["template-region", id]);
export const templateBuiltinCell = (id: string): string => JSON.stringify(["template-builtin", id]);

function object(node: JsonWireNode, omit: readonly string[] = [], replacements: ReadonlyMap<string, string> = new Map()): string {
  return jsonObjectWire([...node.children].flatMap(([key, value]) =>
    typeof key === "string" && !omit.includes(key) ? [[key, replacements.get(key) ?? value.wire] as const] : []));
}
function array(node: JsonWireNode, project: (child: JsonWireNode) => string): string {
  return `[${[...node.children.values()].map(project).join(",")}]`;
}
function ids(node: JsonWireNode): string {
  return array(node, child => jsonWireAt(child, ["id"]).wire);
}
function inline(node: JsonWireNode): string {
  const type = jsonWireAt(node, ["type"]).value;
  if (type === "fact_field") return object(node, ["syncedFactRevision"]);
  if (type === "link" || type === "bound_link") return object(node, [], new Map([
    ["content", array(jsonWireAt(node, ["content"]), inline)],
  ]));
  return node.wire;
}
function blockContent(node: JsonWireNode, type: string): string {
  if (type !== "table") return array(node, inline);
  return object(node, [], new Map([["rows", array(jsonWireAt(node, ["rows"]), row => object(row, [], new Map([
    ["cells", array(jsonWireAt(row, ["cells"]), cell => object(cell, ["revision"], new Map([
      ["content", array(jsonWireAt(cell, ["content"]), inline)],
    ])))],
  ])))]]));
}
function builtin(node: JsonWireNode, kind: BuiltinRecord["kind"]): string {
  const replacements = new Map<string, string>();
  for (const key of fields[kind]) {
    const field = node.children.get(key);
    if (field) replacements.set(key, object(field, ["revision"]));
  }
  if (kind === "employment" || kind === "subproject") replacements.set("periods",
    array(jsonWireAt(node, ["periods"]), period => object(period, ["revision"], new Map(
      ["start", "end", "present"].map(key => [key, object(jsonWireAt(period, [key]), ["revision"])]),
    ))));
  return object(node, ["revision"], replacements);
}

/** These cells describe UI consistency only. Canonical facts and inverses stay in Python. */
export async function projectTemplateUi(input: JsonWireNode): Promise<TemplateUiProjection> {
  const root = parseJsonWire(input.wire), response = await templateProjectWire(root);
  const project = response?.workspace.project;
  if (!project || !response.presentation) throw new Error("INVALID_RESULT");
  const cells = new Map<string, CellValue>();
  const document = jsonWireAt(root, ["workspace", "project", "document"]);
  cells.set("template-regions", ids(jsonWireAt(document, ["regions"])));
  function blocks(nodes: JsonWireNode, values: RichDocumentV2["regions"][number]["blocks"]): void {
    for (const [index, block] of values.entries()) {
      const node = jsonWireAt(nodes, [index]), children = jsonWireAt(node, ["children"]);
      const key = templateBlockCell(block.id);
      if (cells.has(key)) throw new Error("INVALID_RESULT");
      cells.set(key, object(node, ["revision"], new Map([
        ["children", ids(children)], ["content", blockContent(jsonWireAt(node, ["content"]), block.type)],
      ])));
      blocks(children, block.children);
    }
  }
  for (const [index, region] of project.document.regions.entries()) {
    const node = jsonWireAt(document, ["regions", index]), key = templateRegionCell(region.id);
    if (cells.has(key)) throw new Error("INVALID_RESULT");
    cells.set(key, object(node, ["revision"], new Map([["blocks", ids(jsonWireAt(node, ["blocks"]))]])));
    blocks(jsonWireAt(node, ["blocks"]), region.blocks);
  }
  const records = jsonWireAt(root, ["workspace", "project", "facts", "records"]);
  cells.set("template-builtin-order", ids(records));
  for (const [index, record] of project.facts.records.entries()) {
    const key = templateBuiltinCell(record.id);
    if (cells.has(key)) throw new Error("INVALID_RESULT");
    cells.set(key, builtin(jsonWireAt(records, [index]), record.kind));
  }
  return { projectId: response.workspace.projectId, responseWire: root.wire,
    packageWire: jsonWireAt(root, ["workspace", "project", "templatePackage"]).wire, cells };
}

export function templateUiChanges(before: TemplateUiProjection, after: TemplateUiProjection): CellChange[] {
  if (before.projectId !== after.projectId || before.packageWire !== after.packageWire) throw new Error("DEPENDENCY_CHANGED");
  return [...new Set([...before.cells.keys(), ...after.cells.keys()])].flatMap(key => {
    const old = before.cells.get(key) ?? null, next = after.cells.get(key) ?? null;
    return old === next ? [] : [{ key, before: old, after: next }];
  });
}
