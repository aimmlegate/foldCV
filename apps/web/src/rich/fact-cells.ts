import type { WorkingFacts } from "../contracts/generated/working_facts";
import { validateWorkingFacts } from "./validate";
import type { CellValue } from "./history";
import { stableJson } from "./json";

function object(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
export function semantic(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(semantic);
  if (object(value)) return Object.fromEntries(Object.entries(value).filter(([key]) => key !== "revision" && key !== "syncedFactRevision")
    .map(([key, item]) => [key, semantic(item)]));
  return value;
}
function field(value: unknown): value is Record<string, unknown> { return object(value) && "rawText" in value && "status" in value; }
function encode(value: unknown): string { return stableJson(semantic(value)); }
export const factFieldCell = (record: string, key: string): string => `fact-field:${JSON.stringify([record, key])}`;
export function factCells(facts: WorkingFacts): Map<string, CellValue> {
  const result = new Map<string, CellValue>([["fact-order", JSON.stringify(facts.records.map(record => record.id))]]);
  for (const record of facts.records) {
    const metadata: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(record)) {
      if (field(value)) result.set(factFieldCell(record.id, key), encode(value));
      else if (key === "periods" && Array.isArray(value)) {
        metadata[key] = value.map((period: unknown) => {
          if (!object(period) || typeof period["id"] !== "string") throw new Error("Invalid fact period");
          const parts: Record<string, unknown> = {};
          for (const [part, item] of Object.entries(period)) {
            if (field(item)) result.set(factFieldCell(record.id, `period:${period["id"]}:${part}`), encode(item));
            else parts[part] = item;
          }
          return parts;
        });
      } else metadata[key] = value;
    }
    result.set(`fact:${record.id}`, encode(metadata));
  }
  return result;
}
function decode(value: CellValue | undefined): unknown { return value ? JSON.parse(value) as unknown : null; }
export function factsFromCells(cells: ReadonlyMap<string, CellValue>, baseline: WorkingFacts): WorkingFacts {
  const order = decode(cells.get("fact-order"));
  if (!Array.isArray(order) || !order.every((id: unknown) => typeof id === "string")) throw new Error("Invalid fact order");
  const records = order.map((id: string) => {
    const meta = decode(cells.get(`fact:${id}`));
    if (!object(meta)) throw new Error("Missing fact metadata");
    const record: Record<string, unknown> = { ...meta, revision: 1 };
    for (const [key, value] of cells) if (key.startsWith("fact-field:")) {
      const pair: unknown = JSON.parse(key.slice("fact-field:".length));
      if (!Array.isArray(pair) || pair[0] !== id || typeof pair[1] !== "string" || !value) continue;
      const data = decode(value);
      if (!object(data)) throw new Error("Invalid working field");
      if (!pair[1].startsWith("period:")) record[pair[1]] = { ...data, revision: 1 };
    }
    if (Array.isArray(record["periods"])) record["periods"] = record["periods"].map((period: unknown) => {
      if (!object(period) || typeof period["id"] !== "string") throw new Error("Invalid period metadata");
      const parts: Record<string, unknown> = { ...period, revision: 1 };
      for (const part of ["start", "end", "present"]) {
        const data = decode(cells.get(factFieldCell(id, `period:${period["id"]}:${part}`)));
        if (!object(data)) throw new Error("Missing period field");
        parts[part] = { ...data, revision: 1 };
      }
      return parts;
    });
    return record;
  });
  const value: unknown = { revision: baseline.revision, records, tombstones: baseline.tombstones.filter(item => !order.includes(item.recordId)) };
  if (!validateWorkingFacts(value)) throw new Error("Invalid working facts");
  return value;
}
