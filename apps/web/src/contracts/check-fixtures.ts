import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { validateContract, validateExtractResult, validateRenderRequest } from "./validate.js";

type Edit = { op: "set" | "remove" | "append" | "clone" | "repeat_text" | "fill_sidebar"; path: (string | number)[]; value?: unknown; from?: (string | number)[]; text?: string; count?: number; repeat?: number; items?: number; sections?: number };
type Case = { name: string; contract: string; base: string; valid: boolean; edits: Edit[] };

const here = dirname(fileURLToPath(import.meta.url));
const examples = resolve(here, "../../../../contracts/examples");
function read(name: string): unknown {
  return JSON.parse(readFileSync(resolve(examples, name), "utf8")) as unknown;
}
function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("fixture object expected");
  return value as Record<string, unknown>;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error("fixture array expected");
  return value as unknown[];
}
function child(value: unknown, key: string | number): unknown {
  return typeof key === "number" ? array(value)[key] : record(value)[key];
}
function edit(data: unknown, change: Edit): void {
  const parent = change.path.slice(0, -1).reduce<unknown>((value, key) => child(value, key), data);
  const key = change.path.at(-1);
  if (key === undefined) throw new Error("empty edit path");
  if (change.op === "clone") {
    if (change.from === undefined) throw new Error("clone source missing");
    const source = change.from.reduce<unknown>((value, part) => child(value, part), data);
    array(child(parent, key)).push(structuredClone(source));
    return;
  }
  if (change.op === "repeat_text") {
    if (change.text === undefined || change.count === undefined) throw new Error("repeat data missing");
    if (typeof key === "number") array(parent)[key] = change.text.repeat(change.count);
    else record(parent)[key] = change.text.repeat(change.count);
    return;
  }
  if (change.op === "fill_sidebar") {
    if (change.text === undefined || change.repeat === undefined || change.items === undefined || change.sections === undefined) throw new Error("sidebar data missing");
    record(parent)[String(key)] = Array.from({ length: change.sections }, () => ({ title: "T", items: Array.from({ length: change.items! }, () => change.text!.repeat(change.repeat!)) }));
    return;
  }
  if (change.op === "append") { array(child(parent, key)).push(change.value); return; }
  if (typeof key === "number") {
    const target = array(parent);
    if (change.op === "remove") target.splice(key, 1);
    else target[key] = change.value;
  } else {
    const target = record(parent);
    if (change.op === "remove") delete target[key];
    else target[key] = change.value;
  }
}
const project = read("project.json");
const zip = read("zip_manifest.json");
const render = read("render_request.json");
const prepare = read("prepare_request.json");
const extract = read("extract_result.json");
const bases: Record<string, unknown> = { project, proposal: child(child(project, "proposals"), 0), template: child(project, "template"), zip_manifest: zip, render_request: render, prepare_request: prepare, extract_result: extract };
const cases = array(read("cases.json")) as Case[];
for (const test of cases) {
  const source = bases[test.base];
  if (source === undefined) throw new Error(`unknown fixture base ${test.base}`);
  const data: unknown = structuredClone(source);
  for (const change of test.edits) edit(data, change);
  const valid = test.contract === "render_request" ? await validateRenderRequest(data)
    : test.contract === "extract_result" ? validateExtractResult(data) : validateContract(test.contract, data);
  assert.equal(valid, test.valid, test.name);
}
process.stdout.write(`${cases.length} shared browser contract cases passed\n`);
