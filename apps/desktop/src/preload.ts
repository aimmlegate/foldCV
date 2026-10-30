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
