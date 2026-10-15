import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type Plugin } from "vite";
import { fileURLToPath } from "node:url";

function proofBoundary(mode: string): Plugin {
  return { name: "foldcv-uir-boundary", generateBundle() {
    if (mode !== "uir-proof") return;
    const entry = fileURLToPath(new URL("./uir-proof.html", import.meta.url));
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const visited = new Set<string>();
    const visit = (id: string) => {
      if (visited.has(id)) return;
      visited.add(id);
      const module = this.getModuleInfo(id);
      [...(module?.importedIds ?? []), ...(module?.dynamicallyImportedIds ?? [])].forEach(visit);
    };
    visit(entry);
    const modules = [...visited].map(id => id.startsWith(root) ? id.slice(root.length) : id).sort();
    const forbidden = modules.filter(id => /src\/(shell\/theme\.css|next\/next\.css|rich\/(editor|shell)\.css)|future-editor\/(prototype\.js|agent-chat\.js|visual\/index\.js)|tailwindcss\/preflight/.test(id));
    if (forbidden.length) this.error(`UIR stylesheet/runtime boundary: ${forbidden.join(", ")}`);
    this.emitFile({ type: "asset", fileName: "uir-proof-imports.json", source: JSON.stringify({ entry: "uir-proof.html", forbidden, modules }, null, 2) });
  } };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), proofBoundary(mode)],
  server: { host: "127.0.0.1", fs: { allow: [
    fileURLToPath(new URL("./", import.meta.url)),
    fileURLToPath(new URL("../../contracts", import.meta.url)),
    fileURLToPath(new URL("../../templates/foldcv-reference", import.meta.url)),
    fileURLToPath(new URL("../../skills/format-resume/assets", import.meta.url)),
    fileURLToPath(new URL("../../design/future-editor/visual", import.meta.url)),
  ] } },
  build: { target: "es2022", cssCodeSplit: true, manifest: mode === "uir-proof", rollupOptions: { input: {
    main: fileURLToPath(new URL("./index.html", import.meta.url)),
    legacy: fileURLToPath(new URL("./legacy.html", import.meta.url)),
    next: fileURLToPath(new URL("./next.html", import.meta.url)),
    ...(mode === "uir-proof" ? { uirProof: fileURLToPath(new URL("./uir-proof.html", import.meta.url)) } : {}),
  } } },
}));
