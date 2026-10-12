import { createRoot } from "react-dom/client";
import { App } from "./App";
import { exchangeSession, errorLabel } from "./api";
import "./next.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element is missing");
try { await exchangeSession(); createRoot(root).render(<App />); }
catch (error) { createRoot(root).render(<main data-app="foldcv-next"><p role="alert">{errorLabel(error)}</p></main>); }
