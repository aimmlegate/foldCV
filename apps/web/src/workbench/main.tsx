import { createRoot } from "react-dom/client";
import { exchangeSession } from "../api/client";
import { claimApplicationTab, type TabLease } from "./tab";
import { App } from "./App";
import { BlockedTab } from "./BlockedTab";
import "./styles/index.css";

const element = document.getElementById("root");
if (!element) throw new Error("Root is missing");
const root = createRoot(element);

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
    if (!leaving) root.render(<p role="alert">Откройте приложение по адресу из запуска сервиса.</p>);
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
