import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const worker = fileURLToPath(new URL("./workspace-lifecycle.worker.ts", import.meta.url));
const scenarios = [
  ...["open", "upload", "fresh", "remove", "archive", "lifecycle"].flatMap(action =>
    ["navigate", "assistant", "remount"].map(wait => `${action}:${wait}`)),
  "failed-leave", "pending-delete", "pending-open", "new-action-lock", "fresh-reopen", "switch-open", "upload-archive",
  "delete-cleanup-failed", "export-refresh-failed",
  "import-background", "import-failed", "import-refused", "import-delete", "import-restart",
];
for (const scenario of scenarios) test(`workspace hook lifecycle: ${scenario}`, () => {
  const result = spawnSync(process.execPath, ["--experimental-test-module-mocks", "--import", "tsx", worker, scenario],
    { encoding: "utf8", timeout: 15_000 });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
});
