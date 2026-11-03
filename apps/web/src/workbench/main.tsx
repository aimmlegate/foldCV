import { createRoot } from "react-dom/client";
import { exchangeSession } from "../api/client";
import { claimApplicationTab, type TabLease } from "./tab";
import { App } from "./App";
import { BlockedTab } from "./BlockedTab";
import { applyAppearance, readAppearance } from "./settings/interface";
import "./styles/index.css";

const element = document.getElementById("root");
if (!element) throw new Error("Root is missing");
const root = createRoot(element);
// The saved text size and contrast apply before anything is drawn, so no screen flashes the defaults.
applyAppearance(readAppearance());

async function mountApplication(lease: TabLease, host: HTMLElement): Promise<void> {
  const portalHost = document.createElement("div");
  portalHost.dataset["uirEngineUi"] = "true";
  let leaving = false;
  window.addEventListener("pagehide", () => {
    leaving = true; host.inert = true;
    // Let the editor send its unload checkpoint before releasing the tab.
    queueMicrotask(() => { root.unmount(); portalHost.remove(); lease.release(); });
  }, { once: true });
  window.addEventListener("pageshow", event => { if (event.persisted) location.reload(); });
  try {
    await exchangeSession();
    if (leaving) return;
    document.body.append(portalHost); root.render(<App portalHost={portalHost} />);
  } catch {
    lease.release();
    if (!leaving) root.render(<p role="alert">Откройте FoldCV по ссылке, выданной при запуске.</p>);
  }
}

try {
  const lease = await claimApplicationTab();
  if (lease) await mountApplication(lease, element);
  else {
    history.replaceState(null, "", location.pathname + location.search);
    root.render(<BlockedTab />);
  }
} catch {
  history.replaceState(null, "", location.pathname + location.search);
  root.render(<BlockedTab unavailable />);
}
