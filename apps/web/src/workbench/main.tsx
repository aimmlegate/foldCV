import { createRoot } from "react-dom/client";
import { exchangeSession } from "../api/client";
import { App } from "./App";
import "./styles/index.css";

const portalHost = document.createElement("div");
portalHost.dataset["uirEngineUi"] = "true";
document.body.append(portalHost);
const root = document.getElementById("root");
if (!root) throw new Error("Root is missing");
try { await exchangeSession(); createRoot(root).render(<App portalHost={portalHost} />); }
catch { createRoot(root).render(<p role="alert">Откройте приложение по адресу из запуска сервиса.</p>); }
