// Package the macOS app around a built helper, sign it ad hoc and wrap it in a DMG.
// Usage: node scripts/package.mjs <FoldCV Helper.app> <new output directory>
import { flipFuses, FuseV1Options, FuseVersion } from "@electron/fuses";
import { packager } from "@electron/packager";
import { build } from "esbuild";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rename, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktop = fileURLToPath(new URL("../", import.meta.url)), root = resolve(desktop, "../..");
const [helperArgument, outputArgument] = process.argv.slice(2);
if (!helperArgument?.endsWith(".app") || !outputArgument) throw new Error("Usage: package.mjs <FoldCV Helper.app> <output directory>");
const helper = resolve(helperArgument), output = resolve(outputArgument);
if (existsSync(output)) throw new Error("The output directory must not exist yet");
const { version, devDependencies } = JSON.parse(await readFile(join(desktop, "package.json"), "utf8"));
const electron = devDependencies.electron, name = "FoldCV Local";

function run(command, ...args) {
  const result = spawnSync(command, args, { stdio: ["ignore", "inherit", "inherit"] });
  if (result.status !== 0) throw new Error(`${basename(command)} ${args[0]} failed`);
}
const git = (...args) => spawnSync("git", args, { cwd: root, encoding: "utf8" }).stdout.trim();
const sha256 = async path => createHash("sha256").update(await readFile(path)).digest("hex");

// The Electron archive is kept under .tools and checked against the checksums of the electron package.
const archive = `electron-v${electron}-darwin-arm64.zip`, cache = join(root, ".tools/electron");
await mkdir(cache, { recursive: true });
if (!existsSync(join(cache, archive))) {
  run("/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--output", join(cache, archive + ".part"),
    `https://github.com/electron/electron/releases/download/v${electron}/${archive}`);
  await rename(join(cache, archive + ".part"), join(cache, archive));
}
const checksums = JSON.parse(await readFile(join(desktop, "node_modules/electron/checksums.json"), "utf8"));
if (await sha256(join(cache, archive)) !== checksums[archive]) throw new Error("Electron archive checksum mismatch");

const work = await mkdtemp(join(tmpdir(), "foldcv-package-"));
try {
  for (const [entry, file] of [["src/main.ts", "main.cjs"], ["src/preload.ts", "preload.cjs"]]) {
    await build({ absWorkingDir: desktop, entryPoints: [entry], outfile: join(work, "app", file), bundle: true,
      platform: "node", target: "node22", format: "cjs", external: ["electron"], logLevel: "warning" });
  }
  await writeFile(join(work, "app/package.json"), JSON.stringify({ name: "foldcv-local", version, main: "main.cjs" }) + "\n");
  const [packaged] = await packager({ dir: join(work, "app"), out: join(work, "package"), name, executableName: name,
    platform: "darwin", arch: "arm64", electronVersion: electron, electronZipDir: cache, appBundleId: "invalid.foldcv.local",
    appVersion: version, buildVersion: version, appCategoryType: "public.app-category.productivity", asar: true,
    prune: false, overwrite: false, icon: join(root, "assets/branding/foldcv/liquid-glass-v2/macos/FoldCV-native-olive.icns") });
  await mkdir(output, { recursive: true });
  const application = join(output, name + ".app");
  // ditto keeps the helper's relative links, modes and signatures.
  run("/usr/bin/ditto", join(packaged, name + ".app"), application);
  run("/usr/bin/ditto", helper, join(application, "Contents/Helpers/FoldCV Helper.app"));
  await flipFuses(application, { version: FuseVersion.V1, resetAdHocDarwinSignature: true,
    [FuseV1Options.RunAsNode]: false, [FuseV1Options.EnableCookieEncryption]: false,
    [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false, [FuseV1Options.EnableNodeCliInspectArguments]: false,
    [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true, [FuseV1Options.OnlyLoadAppFromAsar]: true,
    [FuseV1Options.GrantFileProtocolExtraPrivileges]: false });
  run("/usr/bin/codesign", "--force", "--deep", "--sign", "-", application);
  run("/usr/bin/codesign", "--verify", "--deep", "--strict", application);

  const volume = join(work, "volume"), mount = join(work, "mount"), dmg = join(output, `${name} ${version}.dmg`);
  await mkdir(volume);
  run("/usr/bin/ditto", application, join(volume, name + ".app"));
  await symlink("/Applications", join(volume, "Applications"));
  run("/usr/bin/hdiutil", "create", "-quiet", "-volname", `${name} ${version}`, "-fs", "HFS+", "-format", "UDZO",
    "-srcfolder", volume, dmg);
  run("/usr/bin/hdiutil", "verify", "-quiet", dmg);
  run("/usr/bin/hdiutil", "attach", "-quiet", "-nobrowse", "-readonly", "-mountpoint", mount, dmg);
  try { run("/usr/bin/codesign", "--verify", "--deep", "--strict", join(mount, name + ".app")); }
  finally { run("/usr/bin/hdiutil", "detach", "-quiet", mount); }

  const info = { application: name, version, commit: git("rev-parse", "HEAD"), dirty: git("status", "--porcelain") !== "",
    electron, dmg: basename(dmg), dmgBytes: (await stat(dmg)).size, dmgSha256: await sha256(dmg),
    signature: "ad-hoc", builtAt: new Date().toISOString() };
  await writeFile(join(output, "build-info.json"), JSON.stringify(info, null, 2) + "\n");
  console.log(dmg);
} finally {
  await rm(work, { recursive: true, force: true });
}
