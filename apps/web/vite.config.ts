import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", fs: { allow: [
    fileURLToPath(new URL("./", import.meta.url)),
    fileURLToPath(new URL("../../contracts", import.meta.url)),
    fileURLToPath(new URL("../../templates/foldcv-reference", import.meta.url)),
    fileURLToPath(new URL("../../skills/format-resume/assets", import.meta.url)),
  ] } },
  build: { target: "es2022", rollupOptions: { input: {
    main: fileURLToPath(new URL("./index.html", import.meta.url)),
    legacy: fileURLToPath(new URL("./legacy.html", import.meta.url)),
    next: fileURLToPath(new URL("./next.html", import.meta.url)),
  } } },
});
