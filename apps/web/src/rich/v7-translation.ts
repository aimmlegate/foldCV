import type { WriterCaptureClipboardV2 } from "../contracts/generated/background_writer_capture_clipboard_v2";
import type { PreparedAddressMapV1 } from "../contracts/generated/template_address_map_v1";
import type { TemplateEditPreparationV1 } from "../contracts/generated/template_edit_preparation_v1";
import { jsonWireAt, type JsonWireNode } from "../contracts/lossless-json";
import { addressLeaves, contentText, leafTarget, responseBlocks, type AddressLeaf } from "../contracts/template-address";

type Operation = TemplateEditPreparationV1["operations"][0];
type ReplaceText = Extract<Operation, { kind: "replace_text" }>;
type PanelRequest = Extract<Operation, { kind: "builtin_panel" }>["command"];
type PasteInline = Extract<Operation, { kind: "paste_inline" }>;
type Capture = TemplateEditPreparationV1["capture"];
/** A panel command before its revisions and capture are bound at issue time. */
export type PanelCommandV7 = Omit<PanelRequest, "capture" | "factsRevision" | "documentRevision">;
type Styles = ReplaceText["styles"];
type Target = NonNullable<ReplaceText["range"]["insertionTarget"]>;
type AddressEntry = PreparedAddressMapV1["containers"][number];

export type LocalContainer = { blockId: string; kind: "content" | "caption" | "cell"; cellId: string | null };
export type Side = "before" | "after" | "interior" | "anchor";
export type V7Operation =
  | { kind: "replace_text"; container: LocalContainer; start: number; end: number; text: string; styles: Styles; side: Side | null }
  | { kind: "set_marks"; container: LocalContainer; start: number; end: number; styles: Styles }
  | { kind: "split_block"; container: LocalContainer; offset: number; created: string }
  | { kind: "merge_blocks"; leading: LocalContainer; trailing: LocalContainer }
  | { kind: "builtin_panel"; command: PanelCommandV7 }
  | { kind: "delete_entity"; recordId: string }
  // Structure commands are not optimistic: they name editor blocks and run after typing drains.
  | { kind: "move_block"; blockId: string; placement: Placement }
  | { kind: "remove_occurrences"; blockIds: string[] }
  | { kind: "set_link_target"; blockId: string; occurrenceId: string; href: string }
  | { kind: "paste_blocks"; clipboardCaptureId: string; placement: Placement }
  | { kind: "paste_inline"; container: LocalContainer; start: number; end: number; side: Side | null; source: PasteInline["source"] };
export type Placement = { parentId: string; afterId: string | null };
/** A copy source in editor coordinates; its texts must equal the verified ones when it is captured. */
export type ClipboardSource = { kind: "range"; container: LocalContainer; start: number; end: number; prior: string }
  | { kind: "blocks"; blockIds: string[] };
type ClipboardSelection = WriterCaptureClipboardV2["selection"];
/** Prior texts are the optimistic container texts this intent was expressed against. */
export type V7Intent = { localId: string; operation: V7Operation; prior: ReadonlyMap<string, string> };
export type Translation = { kind: "operation"; operation: Operation } | { kind: "conflict"; reason: string };
export type Basis = { response: JsonWireNode; map: PreparedAddressMapV1 | null; locals: ReadonlyMap<string, string> };

type Container = { blockId: string; revision: number; text: string; leaves: AddressLeaf[]; kind: LocalContainer["kind"]; cellId: string | null };

class Conflict extends Error {}
function conflict(reason: string): never { throw new Conflict(reason); }
function text(node: JsonWireNode, key: string): string {
  const value = jsonWireAt(node, [key]).value;
  return typeof value === "string" ? value : conflict("invalid canonical text");
}

export function containerKey(container: LocalContainer): string {
  return JSON.stringify([container.blockId, container.kind, container.cellId]);
}

function canonicalBlockId(basis: Basis, id: string): string { return basis.locals.get(id) ?? id; }

function resolve(basis: Basis, local: LocalContainer): Container {
  const blockId = canonicalBlockId(basis, local.blockId), block = responseBlocks(basis.response).get(blockId);
  const group = block?.groups.find(value => value.kind === local.kind && (local.kind !== "cell" || value.key === local.cellId));
  if (!block || !group) return conflict("addressed container is not in the verified result");
  const values = addressLeaves(group.content);
  return { blockId, revision: block.revision, kind: local.kind, cellId: local.cellId, leaves: values, text: contentText(group.content) };
}

function entries(basis: Basis, container: Container): AddressEntry[] {
  return (basis.map?.containers ?? []).filter(entry => entry.output.blockId === container.blockId && entry.output.kind === container.kind
    && (entry.output.kind !== "cell" || entry.output.cellId === container.cellId));
}

function owner(leaf: AddressLeaf): string {
  const type = text(leaf.span, "type");
  if (type === "fact_field") return JSON.stringify(["field", text(leaf.span, "occurrenceId")]);
  if (type === "manual_scope") return JSON.stringify(["scope", text(leaf.span, "scopeId"), text(leaf.span, "occurrenceId")]);
  return JSON.stringify(["literal", leaf.owner ? leaf.path[0] ?? -1 : null]);
}

/** Address a collapsed insertion by offset and side through the verified map, never by wording. */
function target(container: Container, mapped: AddressEntry[], offset: number, side: Side): Target {
  const segments = mapped.flatMap(entry => entry.segments), boundaries = mapped.flatMap(entry => entry.boundaries);
  const nonempty = container.leaves.filter(leaf => leaf.end > leaf.start);
  const chosen = (value: Target | null | undefined): Target => value ?? conflict("unsupported insertion target");
  if (side === "anchor") {
    const listed = segments.filter(segment => segment.result.start === offset && segment.result.end === offset);
    const anchors = container.leaves.filter(leaf => leaf.start === offset && leaf.end === offset);
    if (anchors.length !== 1) return conflict("ambiguous or missing empty anchor");
    const [anchor] = anchors;
    if (!anchor) return conflict("missing empty anchor");
    return listed.length ? chosen(listed.length === 1 ? listed[0]?.target : null) : chosen(leafTarget(anchor));
  }
  const inside = nonempty.find(leaf => leaf.start < offset && offset < leaf.end);
  const left = offset === 0 ? null : nonempty.find(leaf => leaf.end === offset);
  const right = offset === container.text.length ? null : nonempty.find(leaf => leaf.start === offset);
  // The editor saw one node across this offset; the result may have cut it into pieces of one owner only.
  const sameOwner = inside !== undefined || !!left && !!right && owner(left) === owner(right);
  // A server boundary decides first, even inside one leaf, so a withheld (null) address stays withheld.
  const boundary = boundaries.find(value => value.offset === offset);
  if (boundary) {
    if (side === "before") return chosen(boundary.before);
    if (side === "after") return chosen(boundary.after);
    if (!sameOwner) return conflict("interior input now spans different owners");
    return chosen(boundary.before && boundary.after ? boundary.before : null);
  }
  const covering = segments.find(value => value.result.start < offset && offset < value.result.end);
  if (covering) return chosen(covering.target);
  if (inside) return chosen(leafTarget(inside));
  if (side === "before") return chosen(offset === 0 ? { kind: "literal" } : left ? leafTarget(left) : null);
  if (side === "after") return chosen(offset === container.text.length ? { kind: "literal" } : right ? leafTarget(right) : null);
  if (!sameOwner || !left || !right) return conflict("interior input now spans different owners");
  const before = leafTarget(left), after = leafTarget(right);
  return chosen(before && after ? before : null);
}

function range(container: Container, start: number, end: number, insertion?: Target): ReplaceText["range"] {
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end < start || end > container.text.length
    || [start, end].some(point => {
      const left = container.text.charCodeAt(point - 1), right = container.text.charCodeAt(point);
      return left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff;
    })) return conflict("invalid UTF-16 range");
  const value: ReplaceText["range"] = { blockId: container.blockId, beforeRevision: container.revision,
    cellId: container.kind === "cell" ? container.cellId : null, field: container.kind === "caption" ? "caption" : "content", start, end };
  if (insertion) value.insertionTarget = insertion;
  return value;
}

function checked(basis: Basis, intent: V7Intent, local: LocalContainer): Container {
  const container = resolve(basis, local);
  // Any addressed output without correspondence keeps the input, whatever the operation.
  if (entries(basis, container).some(entry => entry.correspondence === "none")) return conflict("server offered no correspondence");
  if (intent.prior.get(containerKey(local)) !== container.text) return conflict("verified text differs from optimistic text");
  return container;
}

function revisions(basis: Basis): { facts: number; document: number; records: Map<string, number> } {
  const workspace = jsonWireAt(basis.response, ["workspace"]), facts = jsonWireAt(workspace, ["project", "facts"]);
  const number = (node: JsonWireNode): number => typeof node.value === "number" ? node.value : conflict("invalid canonical revision");
  const records = new Map<string, number>();
  for (const key of ["records", "extensions"]) for (const record of jsonWireAt(facts, [key]).children.values())
    records.set(text(record, "id"), number(jsonWireAt(record, ["revision"])));
  return { facts: number(jsonWireAt(facts, ["revision"])), document: number(jsonWireAt(workspace, ["documentRevision"])), records };
}

type BlockTargets = Extract<ClipboardSelection, { kind: "blocks" }>["blocks"];
function blockTargets(basis: Basis, ids: readonly string[]): BlockTargets {
  const [first, ...rest] = ids.map(id => blockTarget(basis, id));
  return first ? [first, ...rest] : conflict("no blocks named");
}

function blockTarget(basis: Basis, id: string): { blockId: string; beforeRevision: number } {
  const blockId = canonicalBlockId(basis, id), block = responseBlocks(basis.response).get(blockId);
  return block ? { blockId, beforeRevision: block.revision } : conflict("addressed block is not in the verified result");
}

function placement(basis: Basis, value: Placement): Placement {
  const parentId = canonicalBlockId(basis, value.parentId), afterId = value.afterId === null ? null : canonicalBlockId(basis, value.afterId);
  const regions = new Set([...jsonWireAt(basis.response, ["workspace", "project", "document", "regions"]).children.values()]
    .map(region => text(region, "id")));
  const blocks = responseBlocks(basis.response);
  if (!regions.has(parentId) && !blocks.has(parentId) || afterId !== null && !blocks.has(afterId)) return conflict("placement is not in the verified result");
  return { parentId, afterId };
}

/** A selected editor range as Python's authored range, if the verified text still reads as the editor showed it. */
export function verifiedRange(source: { container: LocalContainer; start: number; end: number; prior: string }, basis: Basis):
  ReplaceText["range"] | { conflict: string } {
  try {
    const container = resolve(basis, source.container);
    if (container.text !== source.prior) return conflict("verified text differs from the selected text");
    return range(container, source.start, source.end);
  } catch (error) {
    if (error instanceof Conflict) return { conflict: error.message };
    throw error;
  }
}

/** A copy source as Python's clipboard selection; the range must still read as the editor showed it. */
export function clipboardSelection(source: ClipboardSource, basis: Basis): ClipboardSelection | { conflict: string } {
  try {
    if (source.kind === "blocks") return { kind: "blocks", blocks: blockTargets(basis, source.blockIds) };
    const container = resolve(basis, source.container);
    if (container.kind !== "content") return conflict("only block text is copied");
    if (container.text !== source.prior) return conflict("verified text differs from the copied text");
    return { kind: "range", range: range(container, source.start, source.end) };
  } catch (error) {
    if (error instanceof Conflict) return { conflict: error.message };
    throw error;
  }
}

/** Translate one unissued intent against the verified result of the operation before it.
 * Panel and entity commands are not optimistic: they bind the current revisions and the request's own capture. */
export function translateIntent(intent: V7Intent, basis: Basis, capture: Capture | null = null): Translation {
  try {
    const value = intent.operation, opId = intent.localId;
    if (value.kind === "builtin_panel") {
      if (!capture) return conflict("panel command needs its request capture");
      const current = revisions(basis);
      return { kind: "operation", operation: { kind: "builtin_panel", opId, command: { ...structuredClone(value.command),
        factsRevision: current.facts, documentRevision: current.document, capture: structuredClone(capture) } } };
    }
    if (value.kind === "delete_entity") {
      const revision = revisions(basis).records.get(value.recordId);
      if (revision === undefined) return conflict("deleted entity is not in the verified result");
      return { kind: "operation", operation: { kind: "delete_entity", opId, recordId: value.recordId, beforeRevision: revision } };
    }
    if (value.kind === "move_block") return { kind: "operation", operation: { kind: "move_block", opId,
      ...blockTarget(basis, value.blockId), placement: placement(basis, value.placement) } };
    if (value.kind === "remove_occurrences") return { kind: "operation", operation: { kind: "remove_occurrences", opId,
      blocks: blockTargets(basis, value.blockIds) } };
    if (value.kind === "set_link_target") return { kind: "operation", operation: { kind: "set_link_target", opId,
      ...blockTarget(basis, value.blockId), occurrenceId: value.occurrenceId, href: value.href } };
    if (value.kind === "paste_blocks") return { kind: "operation", operation: { kind: "paste_blocks", opId,
      source: { kind: "same_project", clipboardCaptureId: value.clipboardCaptureId }, placement: placement(basis, value.placement) } };
    if (value.kind === "paste_inline") {
      const container = checked(basis, intent, value.container);
      if (container.kind !== "content") return conflict("paste goes into block text only");
      if ((value.start === value.end) !== (value.side !== null)) return conflict("collapsed paste needs exactly one side");
      const insertion = value.side ? target(container, entries(basis, container), value.start, value.side) : undefined;
      return { kind: "operation", operation: { kind: "paste_inline", opId, destination: range(container, value.start, value.end, insertion),
        source: structuredClone(value.source) } };
    }
    if (value.kind === "replace_text") {
      const container = checked(basis, intent, value.container);
      const collapsed = value.start === value.end;
      if (collapsed !== (value.side !== null)) return conflict("collapsed input needs exactly one side");
      const insertion = value.side ? target(container, entries(basis, container), value.start, value.side) : undefined;
      return { kind: "operation", operation: { kind: "replace_text", opId, text: value.text, styles: value.styles,
        range: range(container, value.start, value.end, insertion) } };
    }
    if (value.kind === "set_marks") {
      const container = checked(basis, intent, value.container);
      if (value.start === value.end) return conflict("collapsed marks are not an operation");
      return { kind: "operation", operation: { kind: "set_marks", opId, styles: value.styles, range: range(container, value.start, value.end) } };
    }
    if (value.kind === "split_block") {
      const container = checked(basis, intent, value.container);
      if (container.kind !== "content") return conflict("only text blocks split");
      range(container, value.offset, value.offset);
      return { kind: "operation", operation: { kind: "split_block", opId, blockId: container.blockId,
        beforeRevision: container.revision, offset: value.offset } };
    }
    const leading = checked(basis, intent, value.leading), trailing = checked(basis, intent, value.trailing);
    return { kind: "operation", operation: { kind: "merge_blocks", opId, leadingId: leading.blockId, leadingRevision: leading.revision,
      trailingId: trailing.blockId, trailingRevision: trailing.revision } };
  } catch (error) {
    if (error instanceof Conflict) return { kind: "conflict", reason: error.message };
    throw error;
  }
}

/** After a verified result, local blocks created by that intent resolve only through its created entries. */
export function createdLocals(intent: V7Intent, basis: Basis): Map<string, string> | null {
  const value = intent.operation, result = new Map<string, string>();
  if (value.kind !== "split_block") return result;
  const source = canonicalBlockId(basis, value.container.blockId);
  // The created slot must belong to this intent's own operation, not merely to the same source block.
  const created = (basis.map?.containers ?? []).filter(entry => entry.created?.opId === intent.localId
    && entry.input?.blockId === source);
  const [entry] = created;
  if (created.length !== 1 || !entry) return null;
  result.set(value.created, entry.output.blockId);
  return result;
}

/** Bound the changed range between canonical and editor text; ownership stays Python's decision. */
export function correctionRange(canonical: string, editor: string): { start: number; end: number; text: string } | null {
  if (canonical === editor) return null;
  const pair = (text: string, point: number) => {
    const left = text.charCodeAt(point - 1), right = text.charCodeAt(point);
    return left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff;
  };
  let start = 0;
  while (start < canonical.length && start < editor.length && canonical.charCodeAt(start) === editor.charCodeAt(start)) start++;
  while (start > 0 && (pair(canonical, start) || pair(editor, start))) start--;
  let suffix = 0;
  while (suffix < canonical.length - start && suffix < editor.length - start
    && canonical.charCodeAt(canonical.length - 1 - suffix) === editor.charCodeAt(editor.length - 1 - suffix)) suffix++;
  while (suffix > 0 && (pair(canonical, canonical.length - suffix) || pair(editor, editor.length - suffix))) suffix--;
  return { start, end: canonical.length - suffix, text: editor.slice(start, editor.length - suffix) };
}
