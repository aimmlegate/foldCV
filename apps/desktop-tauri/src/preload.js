// What apps/desktop/src/preload.ts gives the page, for the Tauri window: how a download ended, the desktop styles
// and the strip that drags the window, which has no title bar.
(() => {
  const listeners = new Set();
  Object.defineProperty(window, "foldcvDesktop", { value: Object.freeze({
    onDownloadDone(listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  }) });
  // The shell calls this when its save dialog ends.
  Object.defineProperty(window, "__foldcvDownloadDone", { value: (state, name) => {
    for (const listener of [...listeners]) listener(state, name);
  } });
  window.addEventListener("DOMContentLoaded", () => {
    document.documentElement.dataset.desktop = "macos";
    const strip = document.createElement("div");
    strip.className = "desktop-window-drag";
    strip.setAttribute("aria-hidden", "true");
    // Tauri's own script drags the window from elements with this attribute; WebKit has no -webkit-app-region.
    strip.setAttribute("data-tauri-drag-region", "");
    document.body.append(strip);
  });
})();
