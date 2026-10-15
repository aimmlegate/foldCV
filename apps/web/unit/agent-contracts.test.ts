import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { validateContract } from "../src/contracts/validate.js";

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`../../../contracts/examples/agent/${name}.json`, import.meta.url), "utf8")) as unknown;
}

function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return value as Record<string, unknown>;
}

test("agent messages count code points and UTF-8 separately from serialized escaped bytes", () => {
  const message = record(fixture("agent_message"));
  assert.equal(validateContract("agent_message", { ...message, text: "😀".repeat(16_384) }), true);
  assert.equal(validateContract("agent_message", { ...message, text: "😀".repeat(16_384) + "x" }), false);
  assert.equal(validateContract("agent_message", { ...message, text: "\0".repeat(22_000) }), false);
  assert.equal(validateContract("agent_message", { ...message, text: "\ud800" }), false);
  const request = record(fixture("agent_run_request"));
  assert.equal(validateContract("agent_run_request", { ...request, message: "😀".repeat(8000) }), true);
  assert.equal(validateContract("agent_run_request", { ...request, message: "😀".repeat(8001) }), false);
});

test("agent operation count and event discriminators reject overflows and hidden reasoning", () => {
  const prepare = record(fixture("agent_prepare_request"));
  const operations: unknown = prepare.operations;
  assert.ok(Array.isArray(operations));
  const first: unknown = operations[0];
  assert.notEqual(first, undefined);
  assert.equal(validateContract("agent_prepare_request", { ...prepare, operations: Array.from({ length: 100 }, () => structuredClone(first)) }), true);
  assert.equal(validateContract("agent_prepare_request", { ...prepare, operations: Array.from({ length: 101 }, () => structuredClone(first)) }), false);
  const event = record(fixture("agent_event"));
  assert.equal(validateContract("agent_event", { ...event, type: "reasoning.delta", payload: { text: "hidden" } }), false);
  assert.equal(validateContract("agent_event", { ...event, payload: { mutation: {} } }), false);
});

test("agent saved receipts require durable revisions while no-change has no batch", () => {
  const receipt = record(fixture("agent_edit_receipt"));
  assert.equal(validateContract("agent_edit_receipt", receipt), true);
  assert.equal(validateContract("agent_edit_receipt", { ...receipt, durable: false }), false);
  assert.equal(validateContract("agent_edit_receipt", { ...receipt, documentRevision: null }), false);
  assert.equal(validateContract("agent_prepare_result", { disposition: "no_change", batchId: null, affected: [], preview: "" }), true);
  assert.equal(validateContract("agent_prepare_result", { disposition: "no_change", batchId: "fake", affected: [], preview: "" }), false);
});
