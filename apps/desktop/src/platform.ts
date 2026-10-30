import { posix, win32 } from "node:path";

/** The helper executable and its arguments. */
export type HelperCommand = { executable: string; args: string[] };

// Windows variables the frozen service and its workers need; everything else, PATH and PYTHON* included, stays out.
const WINDOWS_VARIABLES = ["SystemRoot", "SystemDrive", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE",
  "HOMEPATH", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
  "CommonProgramFiles", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "USERNAME",
  "USERDOMAIN", "COMPUTERNAME"];

/** Windows variable names ignore case; a plain object does not. */
function variable(environment: NodeJS.ProcessEnv, name: string): string | undefined {
  const key = Object.keys(environment).find(candidate => candidate.toUpperCase() === name.toUpperCase());
  const value = key === undefined ? undefined : environment[key];
  return value ? value : undefined;
}

/** `serve <root>` on the macOS helper app, or on the embeddable Python inside the Windows resources. */
export function helperCommand(platform: NodeJS.Platform, resourcesPath: string, root: string): HelperCommand {
  if (platform === "win32") {
    const helper = win32.join(resourcesPath, "helper");
    return { executable: win32.join(helper, "python", "python.exe"),
      args: ["-X", "utf8", win32.join(helper, "app", "packaging", "helper_entry.py"), "serve", root] };
  }
  return { executable: posix.join(resourcesPath, "../Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper"),
    args: ["serve", root] };
}

export function helperEnvironment(platform: NodeJS.Platform, environment: NodeJS.ProcessEnv,
  home: string): Record<string, string> {
  if (platform !== "win32") {
    const temporary = environment["TMPDIR"];
    return { PATH: "/usr/bin:/bin:/usr/sbin:/sbin", HOME: home, LANG: "en_US.UTF-8",
      ...(temporary ? { TMPDIR: temporary } : {}) };
  }
  const result: Record<string, string> = {};
  for (const name of WINDOWS_VARIABLES) {
    const value = variable(environment, name);
    if (value !== undefined) result[name] = value;
  }
  const system = result["SystemRoot"] ?? result["WINDIR"] ?? "C:\\Windows";
  result["SystemRoot"] = system;
  result["PATH"] = `${system}\\System32;${system};${system}\\System32\\Wbem`;
  return result;
}

/** A drive or UNC path: what the service accepts as an absolute data root on Windows. */
function absolute(platform: NodeJS.Platform, path: string): boolean {
  return platform === "win32" ? /^(?:[a-z]:[\\/]|[\\/]{2}[^\\/])/iu.test(path) : posix.isAbsolute(path);
}

/** FOLDCV_DESKTOP_ROOT for QA runs, else `FoldCV Desktop` in the per-user data folder (local, not roaming, on Windows). */
export function dataRoot(platform: NodeJS.Platform, environment: NodeJS.ProcessEnv, appData: string): string {
  const override = environment["FOLDCV_DESKTOP_ROOT"];
  if (override && absolute(platform, override)) return override;
  if (platform === "win32") return win32.join(variable(environment, "LOCALAPPDATA") ?? appData, "FoldCV Desktop");
  return posix.join(appData, "FoldCV Desktop");
}
