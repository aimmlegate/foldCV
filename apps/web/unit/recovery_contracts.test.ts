import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { openProject } from "../src/project/archive";
import { validateContract } from "../src/contracts/validate";

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`../../../contracts/examples/recovery/${name}.json`, import.meta.url), "utf8")) as unknown;
}

test("recovery versions remain separate from legacy decoders", () => {
  assert.equal(validateContract("project", fixture("project_v4")), false);
  assert.equal(validateContract("project_v4", fixture("project_v4")), true);
  assert.equal(validateContract("workspace_v5", fixture("workspace_v5")), true);
  assert.equal(validateContract("archive_manifest", fixture("archive_manifest_v5")), false);
  assert.equal(validateContract("archive_manifest_v5", fixture("archive_manifest_v5")), true);
});

test("frozen legacy archives retain current content apart from unapplied text", async () => {
  const v4 = await openProject(new Uint8Array(readFileSync(new URL("../../../contracts/examples/recovery/legacy_workspace_v4.foldcv", import.meta.url))));
  assert.equal(v4.editor.project?.views.find((block) => block.id === "profile")?.state.text,
    "Accepted current profile, two trainees.");
  assert.equal(v4.editor.drafts.profile, "Unapplied profile must remain history.");
  const v2 = await openProject(new Uint8Array(readFileSync(new URL("../../../contracts/examples/recovery/legacy_selected_v2.foldcv", import.meta.url))));
  assert.equal(v2.editor.presentation?.name, "Alex Example");
  assert.equal(v2.editor.project?.views.find((block) => block.kind === "job_prose")?.state.text,
    "Python\nBuilt a service at Example Works in 2021.");
});
