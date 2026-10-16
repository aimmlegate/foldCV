import { createRoot } from "react-dom/client";
import { referenceTemplate, referenceVariables } from "./template";
import "../internal/proof-theme.css";
import "./reference-fonts.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing proof root");
createRoot(root).render(<main className="bg-surface text-content" style={{ padding: 24, ...referenceVariables }}>
  <h1>NE03B · Bundled font proof</h1>
  {referenceTemplate.fonts.map(font => <section key={font.face} style={{ margin: "16px 0" }}>
    <p>{font.face} · {font.weight} · Word: {font.wordFamily}{font.wordBold ? " / Bold" : " / Regular"}</p>
    <p data-face={font.face} style={{ fontFamily: font.cssFamily, fontWeight: font.weight, fontSize: "14pt" }}>
      Sample text · Сохранённый текст · 0123456789 · C++ / C# / gRPC
    </p>
  </section>)}
  <p data-face="helvetica" style={{ fontFamily: "Helvetica", fontSize: "14pt" }}>• Native Helvetica bullet</p>
  <p>Fixed columns: {referenceTemplate.regions.sidebar.width} pt / {referenceTemplate.regions.main.width} pt;
    gap {referenceTemplate.regions.gap} pt. Word use/edit/save remains manual.</p>
</main>);
