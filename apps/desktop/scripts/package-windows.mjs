// Package the Windows app around an assembled helper and zip it: a portable folder, no installer, no signature.
// Usage: node scripts/package-windows.mjs <helper directory> <new output directory>
// Runs on macOS and on Windows; Electron's Windows build is downloaded, never run.
import { flipFuses, FuseV1Options, FuseVersion } from "@electron/fuses";
import { packager } from "@electron/packager";
import { build } from "esbuild";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, createWriteStream, existsSync } from "node:fs";
import { cp, mkdir, mkdtemp, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const desktop = fileURLToPath(new URL("../", import.meta.url)), root = resolve(desktop, "../..");
const [helperArgument, outputArgument] = process.argv.slice(2);
if (!helperArgument || !outputArgument) throw new Error("Usage: package-windows.mjs <helper directory> <output directory>");
const helper = resolve(helperArgument), output = resolve(outputArgument);
for (const part of ["python/python.exe", "app/packaging/helper_entry.py"]) {
  if (!existsSync(join(helper, part))) throw new Error("The helper directory has no " + part);
}
if (existsSync(output)) throw new Error("The output directory must not exist yet");
const { version, devDependencies } = JSON.parse(await readFile(join(desktop, "package.json"), "utf8"));
const electron = devDependencies.electron, name = "FoldCV Local";

const git = (...args) => spawnSync("git", args, { cwd: root, encoding: "utf8" }).stdout.trim();
async function sha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

// The Electron archive is kept under .tools and checked against the checksums of the electron package.
const archive = `electron-v${electron}-win32-x64.zip`, cache = join(root, ".tools/electron");
const checksums = JSON.parse(await readFile(join(desktop, "node_modules/electron/checksums.json"), "utf8"));
await mkdir(cache, { recursive: true });
if (!existsSync(join(cache, archive))) {
  const response = await fetch(`https://github.com/electron/electron/releases/download/v${electron}/${archive}`);
  if (!response.ok || !response.body) throw new Error(`Electron download failed: HTTP ${response.status}`);
  await pipeline(Readable.fromWeb(response.body), createWriteStream(join(cache, archive + ".part")));
  await rename(join(cache, archive + ".part"), join(cache, archive));
}
if (await sha256(join(cache, archive)) !== checksums[archive]) throw new Error("Electron archive checksum mismatch");

const work = await mkdtemp(join(tmpdir(), "foldcv-package-"));
try {
  for (const [entry, file] of [["src/main.ts", "main.cjs"], ["src/preload.ts", "preload.cjs"]]) {
    await build({ absWorkingDir: desktop, entryPoints: [entry], outfile: join(work, "app", file), bundle: true,
      platform: "node", target: "node22", format: "cjs", external: ["electron"], logLevel: "warning" });
  }
  await writeFile(join(work, "app/package.json"), JSON.stringify({ name: "foldcv-local", version, main: "main.cjs" }) + "\n");
  // resedit writes the icon, the version strings and the ASAR integrity resource into the exe.
  const [packaged] = await packager({ dir: join(work, "app"), out: join(work, "package"), name, executableName: name,
    platform: "win32", arch: "x64", electronVersion: electron, electronZipDir: cache, appVersion: version,
    buildVersion: version, appCopyright: "FoldCV", asar: true, prune: false, overwrite: false,
    icon: join(root, "assets/branding/foldcv/liquid-glass-v2/windows/FoldCV.ico"),
    win32metadata: { CompanyName: "FoldCV", FileDescription: name, ProductName: name, InternalName: name,
      OriginalFilename: name + ".exe" } });
  await cp(helper, join(packaged, "resources/helper"), { recursive: true, verbatimSymlinks: true, errorOnExist: true,
    force: false });
  await flipFuses(join(packaged, name + ".exe"), { version: FuseVersion.V1,
    [FuseV1Options.RunAsNode]: false, [FuseV1Options.EnableCookieEncryption]: false,
    [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false, [FuseV1Options.EnableNodeCliInspectArguments]: false,
    [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true, [FuseV1Options.OnlyLoadAppFromAsar]: true,
    [FuseV1Options.GrantFileProtocolExtraPrivileges]: false });

  // The zip holds one "FoldCV Local" folder. bsdtar (macOS, Windows 10+) picks the zip format from the suffix; Git for
  // Windows puts GNU tar first on PATH, so the system one is named. No AppleDouble entries from macOS.
  const stage = join(work, "zip"), zip = join(output, `FoldCV-Local-${version}-win-x64.zip`);
  await mkdir(stage);
  await rename(packaged, join(stage, name));
  await mkdir(output, { recursive: true });
  const windows = process.platform === "win32";
  const tar = windows ? join(process.env["SystemRoot"] ?? "C:\\Windows", "System32", "tar.exe") : "/usr/bin/tar";
  const archived = spawnSync(tar, ["-a", "-c", "-f", zip, ...(windows ? [] : ["--no-mac-metadata"]), "-C", stage, name],
    { stdio: ["ignore", "inherit", "inherit"], env: { ...process.env, COPYFILE_DISABLE: "1" } });
  if (archived.status !== 0) throw new Error("tar failed to write the zip");

  const info = { application: name, version, commit: git("rev-parse", "HEAD"), dirty: git("status", "--porcelain") !== "",
    electron, platform: "win32-x64", zip: basename(zip), zipBytes: (await stat(zip)).size, zipSha256: await sha256(zip),
    signature: "none", builtAt: new Date().toISOString() };
  await writeFile(join(output, "build-info.json"), JSON.stringify(info, null, 2) + "\n");
  console.log(zip);
} finally {
  await rm(work, { recursive: true, force: true });
}
