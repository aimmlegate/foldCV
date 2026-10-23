import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { validateContract } from "../src/contracts/validate";
import { validateBackgroundWire } from "../src/contracts/background-validate";

// Snapshots captured from the real app route with a scripted provider (tests/templates/test_template_import_app.py).
const load = (name: string): Record<string, unknown> => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")) as Record<string, unknown>;
const valid = async (value: unknown) => validateContract("background_snapshot_v1", value) && await validateBackgroundWire("background_snapshot_v1", value);

test("template import job snapshots follow Python's rules: tool-free extraction, typed outcome instead of a receipt", async () => {
  const queued = load("template-job-queued.json"), saved = load("template-job-saved.json");
  assert.equal(await valid(queued), true);
  assert.equal(await valid(saved), true);
  const withReceipt = structuredClone(saved); withReceipt["receipt"] = { jobId: saved["id"] };
  assert.equal(await valid(withReceipt), false, "a template job has no receipt");
  const unsaved = structuredClone(saved); (unsaved["templateOutcome"] as Record<string, unknown>)["state"] = "failed_before_replacement";
  assert.equal(await valid(unsaved), false, "publication saved needs a saved outcome");
  const tools = structuredClone(queued); (tools["submission"] as Record<string, unknown>)["tools"] = ["read_import"];
  assert.equal(await valid(tools), false, "template processing is tool-free");
  const legacy = structuredClone(queued); (legacy["submission"] as Record<string, unknown>)["protocol"] = "fixed_v1";
  assert.equal(await valid(legacy), false, "template input needs its protocol");
});
