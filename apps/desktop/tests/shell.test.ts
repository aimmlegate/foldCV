import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { readyLine, startHelper } from "../src/helper.js";
import { dataRoot, helperCommand, helperEnvironment, type HelperCommand } from "../src/platform.js";
import { appUrl, externalUrl } from "../src/policy.js";

const ORIGIN = "http://127.0.0.1:4321", SECRET = "0123456789abcdef0123456789abcdef";
const ENVIRONMENT = helperEnvironment(process.platform, process.env, homedir());

/** A Node script run by this Node, so the fake helpers need no shell on macOS or Windows. */
function fakeHelper(body: string): { command: (root: string) => HelperCommand; directory: string } {
  const directory = mkdtempSync(join(realpathSync(tmpdir()), "foldcv-shell-"));
  const script = join(directory, "helper.cjs");
  writeFileSync(script, body);
  return { command: root => ({ executable: process.execPath, args: [script, "serve", root] }), directory };
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
  const { command, directory } = fakeHelper(`const [mode, root] = process.argv.slice(2);
process.stderr.write("starting " + mode + " " + root + "\\n");
process.stdout.write(${JSON.stringify(JSON.stringify({ origin: ORIGIN, secret: SECRET }) + "\n")});
process.stdin.on("end", () => process.stderr.write("stopped\\n"));
process.stdin.resume();
`);
  const helper = await startHelper(command("/data/root"), ENVIRONMENT, join(directory, "logs", "helper.log"));
  assert.deepEqual(helper.endpoint, { origin: ORIGIN, secret: SECRET });
  await helper.stop();
  assert.equal(await helper.exited, 0);
  assert.equal(readFileSync(join(directory, "logs", "helper.log"), "utf8"), "starting serve /data/root\nstopped\n");
});

test("a helper that exits or answers garbage fails the start", async () => {
  const exits = fakeHelper("process.exit(3);\n");
  const garbage = fakeHelper("process.stdout.write('nonsense\\n');\nprocess.stdin.resume();\n");
  await assert.rejects(startHelper(exits.command("/r"), ENVIRONMENT, join(exits.directory, "helper.log")),
    /HELPER_EXITED/u);
  await assert.rejects(startHelper(garbage.command("/r"), ENVIRONMENT, join(garbage.directory, "helper.log")),
    /HELPER_PROTOCOL/u);
  const missing = { executable: join(exits.directory, "missing"), args: ["serve", "/r"] };
  await assert.rejects(startHelper(missing, ENVIRONMENT, join(exits.directory, "helper.log")),
    /HELPER_(UNAVAILABLE|EXITED)/u);
});

test("each app starts its own helper: the macOS bundle, or the embeddable Python in the Windows resources", () => {
  const resources = "C:\\Apps\\FoldCV Local\\resources", root = "C:\\Users\\a\\AppData\\Local\\FoldCV Desktop";
  assert.deepEqual(helperCommand("win32", resources, root), {
    executable: "C:\\Apps\\FoldCV Local\\resources\\helper\\python\\python.exe",
    args: ["-X", "utf8", "C:\\Apps\\FoldCV Local\\resources\\helper\\app\\packaging\\helper_entry.py", "serve", root] });
  assert.deepEqual(helperCommand("darwin", "/Applications/FoldCV Local.app/Contents/Resources", "/data/root"), {
    executable: "/Applications/FoldCV Local.app/Contents/Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper",
    args: ["serve", "/data/root"] });
});

test("the Windows helper gets only the system variables and the system PATH", () => {
  const environment = helperEnvironment("win32", { SYSTEMROOT: "C:\\Windows", windir: "C:\\Windows",
    TEMP: "C:\\Temp", LocalAppData: "C:\\Users\\a\\AppData\\Local", USERPROFILE: "C:\\Users\\a",
    Path: "C:\\Python313;C:\\Windows\\System32", PYTHONPATH: "C:\\other", PYTHONHOME: "C:\\other",
    NODE_OPTIONS: "--inspect", ELECTRON_RUN_AS_NODE: "1", CODEX_HOME: "C:\\Users\\a\\.codex" }, "ignored");
  assert.deepEqual(environment, { SystemRoot: "C:\\Windows", WINDIR: "C:\\Windows", TEMP: "C:\\Temp",
    LOCALAPPDATA: "C:\\Users\\a\\AppData\\Local", USERPROFILE: "C:\\Users\\a",
    PATH: "C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\Wbem" });
  // A missing SystemRoot still gives the service one.
  assert.equal(helperEnvironment("win32", {}, "ignored")["SystemRoot"], "C:\\Windows");
  assert.deepEqual(helperEnvironment("darwin", { TMPDIR: "/var/folders/t/", PATH: "/opt/homebrew/bin",
    PYTHONPATH: "/other" }, "/Users/a"), { PATH: "/usr/bin:/bin:/usr/sbin:/sbin", HOME: "/Users/a",
    LANG: "en_US.UTF-8", TMPDIR: "/var/folders/t/" });
});

test("the data root is local app data on Windows, Application Support on macOS, or an absolute QA override", () => {
  const roaming = "C:\\Users\\a\\AppData\\Roaming", local = { LOCALAPPDATA: "C:\\Users\\a\\AppData\\Local" };
  assert.equal(dataRoot("win32", local, roaming), "C:\\Users\\a\\AppData\\Local\\FoldCV Desktop");
  assert.equal(dataRoot("win32", {}, roaming), "C:\\Users\\a\\AppData\\Roaming\\FoldCV Desktop");
  assert.equal(dataRoot("win32", { ...local, FOLDCV_DESKTOP_ROOT: "D:\\qa root" }, roaming), "D:\\qa root");
  assert.equal(dataRoot("win32", { FOLDCV_DESKTOP_ROOT: "\\\\server\\share\\qa" }, roaming), "\\\\server\\share\\qa");
  // The service refuses a root without a drive, so the app does not pass one.
  for (const override of ["qa", "\\qa", "/qa", "D:qa"]) {
    assert.equal(dataRoot("win32", { ...local, FOLDCV_DESKTOP_ROOT: override }, roaming),
      "C:\\Users\\a\\AppData\\Local\\FoldCV Desktop", override);
  }
  const support = "/Users/a/Library/Application Support";
  assert.equal(dataRoot("darwin", {}, support), "/Users/a/Library/Application Support/FoldCV Desktop");
  assert.equal(dataRoot("darwin", { FOLDCV_DESKTOP_ROOT: "/private/tmp/qa" }, support), "/private/tmp/qa");
  assert.equal(dataRoot("darwin", { FOLDCV_DESKTOP_ROOT: "qa" }, support),
    "/Users/a/Library/Application Support/FoldCV Desktop");
});
