import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { readyLine, startHelper } from "../src/helper.js";
import { appUrl, externalUrl } from "../src/policy.js";

const ORIGIN = "http://127.0.0.1:4321", SECRET = "0123456789abcdef0123456789abcdef";

function fakeHelper(body: string): { executable: string; directory: string } {
  const directory = mkdtempSync(join(realpathSync(tmpdir()), "foldcv-shell-"));
  const executable = join(directory, "helper");
  writeFileSync(executable, "#!/bin/sh\n" + body + "\n");
  chmodSync(executable, 0o755);
  return { executable, directory };
}

test("the window keeps to its own service and hands web and mail links to the system", () => {
  assert.equal(appUrl(ORIGIN + "/?project=a", ORIGIN), true);
  assert.equal(appUrl("http://127.0.0.1:4322/", ORIGIN), false);
  assert.equal(appUrl("not a url", ORIGIN), false);
  assert.equal(externalUrl("https://example.com/a"), "https://example.com/a");
  assert.equal(externalUrl("mailto:person@example.com"), "mailto:person@example.com");
  for (const raw of ["file:///etc/passwd", "javascript:alert(1)", "https://user:pass@example.com/", "nonsense"]) {
    assert.equal(externalUrl(raw), null, raw);
  }
});

test("the ready line names a loopback origin and a full secret", () => {
  assert.deepEqual(readyLine(JSON.stringify({ origin: ORIGIN, secret: SECRET })), { origin: ORIGIN, secret: SECRET });
  for (const value of [{ origin: "http://localhost:4321", secret: SECRET }, { origin: ORIGIN, secret: "short" }, []]) {
    assert.throws(() => readyLine(JSON.stringify(value)), /HELPER_PROTOCOL/u);
  }
});

test("the helper serves until its stdin closes and logs its stderr", async () => {
  const { executable, directory } = fakeHelper(`echo "starting $1 $2" >&2
echo '{"origin":"${ORIGIN}","secret":"${SECRET}"}'
cat >/dev/null
echo stopped >&2`);
  const helper = await startHelper(executable, "/data/root", join(directory, "logs/helper.log"));
  assert.deepEqual(helper.endpoint, { origin: ORIGIN, secret: SECRET });
  await helper.stop();
  assert.equal(await helper.exited, 0);
  assert.equal(readFileSync(join(directory, "logs/helper.log"), "utf8"), "starting serve /data/root\nstopped\n");
});

test("a helper that exits or answers garbage fails the start", async () => {
  const exits = fakeHelper("exit 3"), garbage = fakeHelper("echo nonsense; cat >/dev/null");
  await assert.rejects(startHelper(exits.executable, "/r", join(exits.directory, "helper.log")), /HELPER_EXITED/u);
  await assert.rejects(startHelper(garbage.executable, "/r", join(garbage.directory, "helper.log")), /HELPER_PROTOCOL/u);
  await assert.rejects(startHelper(join(exits.directory, "missing"), "/r", join(exits.directory, "helper.log")),
    /HELPER_(UNAVAILABLE|EXITED)/u);
});
