import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./shell/App";
import "./shell/theme.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Missing app root");
}
const mount = root;

async function bootstrap() {
  const fragment = window.location.hash;
  const secret = new URLSearchParams(fragment.startsWith("#") ? fragment.slice(1) : fragment).get("secret");
  if (fragment) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  if (secret !== null) {
    try {
      const response = await fetch("/v1/session/exchange", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret }),
      });
      if (!response.ok) throw new Error("Session exchange failed");
    } catch {
      mount.replaceChildren();
      const notice = document.createElement("p");
      notice.setAttribute("role", "alert");
      notice.textContent = "Локальная сессия недоступна. Запустите приложение снова.";
      mount.append(notice);
      return;
    }
  }
  createRoot(mount).render(<React.StrictMode><App /></React.StrictMode>);
}

void bootstrap();
