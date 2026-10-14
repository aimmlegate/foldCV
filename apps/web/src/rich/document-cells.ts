import type { RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { CellValue } from "./history";
import type { RichBlock } from "./save-queue";
import { semantic } from "./fact-cells";
import { stableJson } from "./json";
import { normalizedBlock } from "./normalize";

export type StoredBlock = { block: RichBlock; children: string[] };
export function documentCells(document: RichDocumentV1, cache: Map<string, StoredBlock>): Map<string, CellValue> {
  const values = new Map<string, CellValue>();
  const visit = (block: RichBlock) => {
    const stored: StoredBlock = { block: { ...normalizedBlock(block), children: [], revision: 1 }, children: block.children.map(child => child.id) };
    const json = stableJson(semantic(stored)); cache.set(json, stored); values.set(`block:${block.id}`, json); block.children.forEach(visit);
  };
  document.regions.forEach(region => { values.set(`region:${region.id}`, JSON.stringify(region.blocks.map(block => block.id))); region.blocks.forEach(visit); });
  return values;
}
