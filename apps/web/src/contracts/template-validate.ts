import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import projectSchema from "../../../../contracts/json-schema/template_project_response_v1.schema.json" with { type: "json" };
import writerSchema from "../../../../contracts/json-schema/background_writer_view_v2.schema.json" with { type: "json" };
import mutationSchema from "../../../../contracts/json-schema/template_mutation_v1.schema.json" with { type: "json" };
import type { TemplateProjectResponseV1 } from "./generated/template_project_response_v1";
import type { WriterViewV2 } from "./generated/background_writer_view_v2";
import type { TemplateMutationV1 } from "./generated/template_mutation_v1";
import type { TemplatePackage } from "./generated/template_package";
import { sameValue, sha256 } from "../background/wire";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "./lossless-json";
import { jsonResponseWire } from "./json-response";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const projectShape = ajv.compile<TemplateProjectResponseV1>(taggedSchema(projectSchema));
const writerShape = ajv.compile<WriterViewV2>(taggedSchema(writerSchema));
const mutationShape = ajv.compile<TemplateMutationV1>(taggedSchema(mutationSchema));
const verifiedPackages = new Set<string>();
const packageCapabilities = new Set(["text", "join_fields", "join_items", "bullets", "tags", "period", "link",
  "focus_entry", "object_items", "builtin_mapping", "explicit_item_roots", "fallback_style", "header_slots", "date_text"]);

function base64Bytes(value: string): Uint8Array<ArrayBuffer> {
  const decoded = atob(value);
  if (btoa(decoded) !== value) throw new Error("INVALID_RESULT");
  return Uint8Array.from(decoded, character => character.charCodeAt(0));
}

async function packageIntegrity(value: TemplatePackage, root: JsonWireNode): Promise<boolean> {
  const fingerprint = await sha256(root.wire);
  if (verifiedPackages.has(fingerprint)) return true;
  if (!["template-compiler-1", "template-compiler-2", "template-compiler-3"].includes(value.compilerVersion)
    || value.operationVersion !== "template-operations-1" || value.projectionVersion !== "closed-json-1"
    || value.recipe.schemaVersion !== 1 || value.recipe.renderInputVersion !== 1
    || value.recipe.capabilities.some(capability => !packageCapabilities.has(capability))
    || await sha256(base64Bytes(value.originalBase64)) !== value.originalHash
    || await sha256(jsonWireAt(root, ["definition"]).wire) !== value.configHash
    || value.id !== value.definition.template.id || value.revision !== value.definition.template.revision) return false;
  const declared = new Map(value.definition.assets.map(asset => [asset.id, asset]));
  if (declared.size !== value.definition.assets.length || declared.size !== value.assets.length
    || new Set(value.assets.map(asset => asset.id)).size !== value.assets.length) return false;
  let total = 0;
  for (const asset of value.assets) {
    const source = declared.get(asset.id), bytes = base64Bytes(asset.bytesBase64);
    total += bytes.length;
    if (!source || source.path !== asset.path || source.role !== asset.role || source.mime_type !== asset.mimeType
      || bytes.length !== asset.size || bytes.length > 20 * 1024 * 1024 || total > 40 * 1024 * 1024
      || await sha256(bytes) !== asset.sha256) return false;
  }
  const definition = jsonWireAt(root, ["definition"]), recipe = jsonWireAt(root, ["recipe"]);
  if (jsonWireAt(definition, ["style"]).wire !== jsonWireAt(recipe, ["style"]).wire
    || jsonWireAt(definition, ["layout"]).wire !== jsonWireAt(recipe, ["layout"]).wire) return false;
  for (const [field, target] of [["view", "views"], ["placement", "placements"]] as const) {
    const expected = jsonObjectWire(value.definition.blocks.map((block, index) =>
      [block.id, jsonWireAt(definition, ["blocks", index, field]).wire]));
    if (expected !== jsonWireAt(recipe, [target]).wire) return false;
  }
  const identity = jsonObjectWire([
    ...["configHash", "compilerVersion", "operationVersion", "projectionVersion", "recipe", "blocks", "manifest"]
      .map(key => [key, jsonWireAt(root, [key]).wire] as const),
    ["assets", jsonObjectWire(value.assets.map(asset => [asset.id, JSON.stringify(asset.sha256)]))],
  ]);
  if (await sha256(identity) !== value.packageHash) return false;
  // This checks captured integrity. Compiler derivation and renderer support have separate owners.
  verifiedPackages.add(fingerprint);
  while (verifiedPackages.size > 8) {
    const oldest = verifiedPackages.values().next().value;
    if (oldest !== undefined) verifiedPackages.delete(oldest);
  }
  return true;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function presentationReferences(value: unknown, captured: TemplatePackage): boolean {
  if (Array.isArray(value)) return value.every(part => presentationReferences(part, captured));
  if (!record(value)) return true;
  if ("presentation" in value && typeof value.presentation === "object" && value.presentation !== null) {
    const ref = value.presentation;
    if (!record(ref) || ref.packageHash !== captured.packageHash || typeof ref.viewKey !== "string"
      || typeof ref.styleToken !== "string" || !Object.hasOwn(captured.recipe.views, ref.viewKey)
      || !Object.hasOwn(captured.recipe.style.text, ref.styleToken)) return false;
    const view = captured.recipe.views[ref.viewKey];
    if (ref.nodeIndex !== undefined && ref.nodeIndex !== null && (!Number.isInteger(ref.nodeIndex)
      || typeof ref.nodeIndex !== "number" || ref.nodeIndex < 0 || !view || ref.nodeIndex >= view.nodes.length)) return false;
  }
  return Object.values(value).every(part => presentationReferences(part, captured));
}

export async function templateProjectWire(root: JsonWireNode): Promise<TemplateProjectResponseV1 | null> {
  try {
    const value = root.value;
    if (!projectShape(value)) return null;
    const workspace = value.workspace, project = workspace.project;
    if (value.durability === "durable" && (value.savedProjectRevision !== workspace.projectRevision
      || value.savedDocumentRevision !== workspace.documentRevision)) return null;
    if (!project) {
      const captured = workspace.preDraft?.templatePackage;
      if (captured && !await packageIntegrity(captured, jsonWireAt(root, ["workspace", "preDraft", "templatePackage"]))) return null;
      return value.snapshot === null && value.presentation === null ? value : null;
    }
    const snapshot = value.snapshot, presentation = value.presentation;
    if (!snapshot || !presentation || project.projectId !== workspace.projectId || project.revision !== workspace.projectRevision
      || project.document.revision !== workspace.documentRevision || snapshot.projectId !== workspace.projectId
      || snapshot.projectRevision !== workspace.projectRevision || snapshot.documentRevision !== workspace.documentRevision
      || snapshot.packageHash !== project.templatePackage.packageHash || !sameValue(snapshot, presentation.snapshot)) return null;
    const authored = jsonWireAt(root, ["workspace", "project"]);
    const captured = jsonWireAt(authored, ["templatePackage"]);
    if (!await packageIntegrity(project.templatePackage, captured)
      || await sha256(jsonWireAt(authored, ["document"]).wire) !== snapshot.documentHash
      || await sha256(jsonWireAt(authored, ["facts"]).wire) !== snapshot.factsHash
      || jsonWireAt(root, ["presentation", "recipe"]).wire !== jsonWireAt(captured, ["recipe"]).wire
      || !presentationReferences(project.document, project.templatePackage)) return null;
    const blocks: (readonly [string, string])[] = [];
    function visit(node: JsonWireNode): void {
      if (record(node.value) && "children" in node.value && "provenance" in node.value && "id" in node.value) {
        if (typeof node.value.id !== "string" || node.value.presentation === null) throw new Error("INVALID_RESULT");
        blocks.push([node.value.id, jsonWireAt(node, ["presentation"]).wire]);
      }
      node.children.forEach(visit);
    }
    visit(jsonWireAt(authored, ["document"]));
    const blockWire = jsonObjectWire(blocks);
    if (blockWire !== jsonWireAt(root, ["presentation", "blocks"]).wire
      || await sha256(jsonObjectWire([["blocks", blockWire], ["recipe", jsonWireAt(captured, ["recipe"]).wire]])) !== snapshot.presentationHash) return null;
    return value;
  } catch { return null; }
}

export async function templateProjectReply(value: unknown): Promise<TemplateProjectResponseV1 | null> {
  try { return await templateProjectWire(jsonResponseWire(value)); } catch { return null; }
}

export async function templateWriterReply(value: unknown): Promise<WriterViewV2 | null> {
  try {
    if (!writerShape(value) || await sha256(value.workspaceWire) !== value.workspaceSha256) return null;
    const root = parseJsonWire(value.workspaceWire), workspace = value.response.workspace;
    if (!sameValue(root.value, workspace) || value.writer.projectId !== workspace.projectId
      || value.drafts.some(draft => draft.projectId !== workspace.projectId || draft.lineage !== value.writer.lineage)
      || value.canonicalReady !== (value.response.durability === "durable")) return null;
    const responseRoot = jsonResponseWire(value);
    if (root.wire !== jsonWireAt(responseRoot, ["response", "workspace"]).wire) return null;
    if (!await templateProjectWire(jsonWireAt(responseRoot, ["response"]))) return null;
    if (value.mutationWire !== null && value.mutationWire !== undefined) {
      const mutation: unknown = parseJsonWire(value.mutationWire).value;
      if (!mutationShape(mutation) || !value.canonicalReady || mutation.projectId !== workspace.projectId) return null;
      const checksum = await sha256(value.mutationWire);
      if (!workspace.mutationReplay.some(item => item.clientMutationId === mutation.clientMutationId
        && item.requestSha256 === checksum && item.resultingRevision <= workspace.projectRevision)) return null;
      if (value.localHistoryAck && value.localHistoryAck.actionId !== (mutation.history.originActionId ?? mutation.actionId)) return null;
    } else if (value.localHistoryAck) return null;
    return value;
  } catch { return null; }
}
