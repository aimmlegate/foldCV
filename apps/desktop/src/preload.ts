import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";
import { DOWNLOAD_DONE } from "./policy.js";

// The only thing the page hears from the shell: how a download ended.
contextBridge.exposeInMainWorld("foldcvDesktop", {
  onDownloadDone(listener: (state: string, name: string) => void): () => void {
    const relay = (_event: IpcRendererEvent, state: string, name: string) => listener(state, name);
    ipcRenderer.on(DOWNLOAD_DONE, relay);
    return () => { ipcRenderer.removeListener(DOWNLOAD_DONE, relay); };
  },
});

// Mark the page for its desktop styles. The macOS window has no title bar, so add the strip that drags the window;
// the Windows window keeps its native frame.
const mac = process.platform === "darwin";
window.addEventListener("DOMContentLoaded", () => {
  document.documentElement.dataset["desktop"] = mac ? "macos" : "windows";
  if (!mac) return;
  const strip = document.createElement("div");
  strip.className = "desktop-window-drag";
  strip.setAttribute("aria-hidden", "true");
  document.body.append(strip);
});
