// The window has no title bar: mark the page for its macOS styles and add the strip that drags the window.
window.addEventListener("DOMContentLoaded", () => {
  document.documentElement.dataset["desktop"] = "macos";
  const strip = document.createElement("div");
  strip.className = "desktop-window-drag";
  strip.setAttribute("aria-hidden", "true");
  document.body.append(strip);
});
