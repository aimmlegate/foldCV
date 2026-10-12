import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1" },
  build: { target: "es2022", rollupOptions: { input: {
    legacy: fileURLToPath(new URL("./index.html", import.meta.url)),
    next: fileURLToPath(new URL("./next.html", import.meta.url)),
  } } },
});
