import { app, BrowserWindow, dialog, Menu, screen, session, shell, type BrowserWindowConstructorOptions,
  type MenuItemConstructorOptions, type Session, type WebContents } from "electron";
import { homedir } from "node:os";
import { join } from "node:path";
import { startHelper, type Helper } from "./helper.js";
import { dataRoot, helperCommand, helperEnvironment } from "./platform.js";
import { appUrl, externalUrl } from "./policy.js";

const mac = process.platform === "darwin";
// The service data, the CLI profile and Chromium's own storage share the root of the 0.1 builds; QA runs may set
// FOLDCV_DESKTOP_ROOT to another absolute path.
const root = dataRoot(process.platform, process.env, app.getPath("appData"));
const log = join(root, "logs", "helper.log");
app.setPath("userData", join(root, "electron"));
app.setAppLogsPath(join(root, "logs"));
if (process.platform === "win32") app.setAppUserModelId("invalid.foldcv.local");

let helper: Helper | null = null, stopping: Promise<void> | null = null, finished = false;

function openExternal(raw: string): void {
  const url = externalUrl(raw);
  if (url) void shell.openExternal(url);
}

function secure(owned: Session, origin: string): void {
  owned.setPermissionRequestHandler((_contents, permission, callback, details) =>
    callback(permission === "clipboard-sanitized-write" && appUrl(details.requestingUrl, origin)));
  owned.setPermissionCheckHandler((_contents, permission, requesting) =>
    permission === "clipboard-sanitized-write" && requesting === origin);
  owned.on("will-download", (_event, item) => {
    item.setSaveDialogOptions({ defaultPath: join(app.getPath("downloads"), item.getFilename()) });
  });
}

function guard(contents: WebContents, origin: string): void {
  contents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: "deny" }; });
  const stay = (event: Electron.Event, url: string) => {
    if (!appUrl(url, origin)) { event.preventDefault(); openExternal(url); }
  };
  contents.on("will-navigate", stay);
  contents.on("will-redirect", stay);
  contents.on("will-attach-webview", event => event.preventDefault());
  contents.on("context-menu", (_event, params) => {
    const items: MenuItemConstructorOptions[] = params.dictionarySuggestions.slice(0, 5).map(word =>
      ({ label: word, click: () => contents.replaceMisspelling(word) }));
    if (items.length) items.push({ type: "separator" });
    if (params.isEditable) items.push({ role: "cut", enabled: params.editFlags.canCut });
    items.push({ role: "copy", enabled: params.editFlags.canCopy });
    if (params.isEditable) items.push({ role: "paste", enabled: params.editFlags.canPaste });
    items.push({ type: "separator" }, { role: "selectAll" });
    Menu.buildFromTemplate(items).popup();
  });
}

function menu(): Menu {
  const view: MenuItemConstructorOptions = { label: "View", submenu: [{ role: "reload" }, { type: "separator" },
    { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { type: "separator" }, { role: "togglefullscreen" }] };
  // The app and window menus exist on macOS only; on Windows the menu bar hides until Alt.
  return Menu.buildFromTemplate(mac ? [{ role: "appMenu" }, { role: "fileMenu" }, { role: "editMenu" }, view,
    { role: "windowMenu" }] : [{ role: "fileMenu" }, { role: "editMenu" }, view]);
}

// macOS: no title bar, the window buttons over the page corner. Windows: the native frame.
const frame: BrowserWindowConstructorOptions = mac
  ? { titleBarStyle: "hidden", trafficLightPosition: { x: 16, y: 12 } } : { autoHideMenuBar: true };

function createWindow(origin: string): BrowserWindow {
  const area = screen.getPrimaryDisplay().workAreaSize;
  const window = new BrowserWindow({ width: Math.min(1440, area.width), height: Math.min(960, area.height),
    minWidth: 800, minHeight: 600, show: false, title: "FoldCV", ...frame, backgroundColor: "#eae9e2",
    webPreferences: { preload: join(__dirname, "preload.cjs"), sandbox: true, contextIsolation: true,
      nodeIntegration: false, webSecurity: true, webviewTag: false, devTools: false, navigateOnDragDrop: false } });
  guard(window.webContents, origin);
  window.once("ready-to-show", () => window.show());
  // Unsent edits wait in the page's storage, so a fresh page picks them up.
  window.webContents.on("render-process-gone", (_event, details) => {
    if (details.reason !== "clean-exit" && !stopping) void window.loadURL(origin + "/");
  });
  window.on("closed", () => app.quit());
  return window;
}

function closeWindows(): Promise<void> {
  return Promise.all(BrowserWindow.getAllWindows().map(window => new Promise<void>(resolve => {
    if (window.isDestroyed()) { resolve(); return; }
    window.once("closed", () => resolve());
    // A page that holds the unload never keeps the app open.
    setTimeout(() => { if (!window.isDestroyed()) window.destroy(); }, 5_000);
    window.close();
  }))).then(() => undefined);
}

function shutdown(): Promise<void> {
  stopping ??= closeWindows().then(() => helper?.stop()).finally(() => { finished = true; app.quit(); });
  return stopping;
}

async function fatal(message: string): Promise<void> {
  await dialog.showMessageBox({ type: "error", message, detail: "Подробности в журнале: " + log });
  void shutdown();
}

app.on("before-quit", event => {
  if (finished) return;
  event.preventDefault();
  void shutdown();
});
app.on("second-instance", () => {
  const [window] = BrowserWindow.getAllWindows();
  if (window) { if (window.isMinimized()) window.restore(); window.focus(); }
});

async function start(): Promise<void> {
  await app.whenReady();
  Menu.setApplicationMenu(menu());
  try {
    helper = await startHelper(helperCommand(process.platform, process.resourcesPath, root),
      helperEnvironment(process.platform, process.env, homedir()), log);
  } catch {
    await fatal("Не удалось запустить FoldCV.");
    return;
  }
  const { origin, secret } = helper.endpoint;
  void helper.exited.then(() => { if (!stopping) void fatal("Сервис FoldCV остановился. Приложение будет закрыто."); });
  secure(session.defaultSession, origin);
  await createWindow(origin).loadURL(`${origin}/#secret=${secret}`);
}

if (!app.requestSingleInstanceLock()) { finished = true; app.quit(); }
else void start();
