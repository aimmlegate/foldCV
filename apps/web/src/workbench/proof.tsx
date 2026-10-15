import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import { exchangeSession } from "../next/api";
import { RichEditor, type RichEditorHandle } from "../rich/Editor";
import { download, listProjects, projectRequest } from "../rich/api";
import { Icon } from "./ui/Icon";
import "./styles/index.css";

const portalHost = document.createElement("div");
portalHost.dataset["uirEngineUi"] = "true";
document.body.append(portalHost);

function Proof() {
  const [response, setResponse] = useState<RichProjectResponse | null>(null), [projects, setProjects] = useState<GuiProjectListResponse | null>(null);
  const [status, setStatus] = useState("Открываю…"), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [collapsed, setCollapsed] = useState(() => innerWidth <= 600), [reopen, setReopen] = useState(0);
  const editor = useRef<RichEditorHandle>(null), acting = useRef(false);
  const acknowledge = useCallback((next: RichProjectResponse) => {
    setResponse(next);
    const url = new URL(location.href); url.searchParams.set("project", next.workspace.projectId);
    history.replaceState(null, "", url.pathname + url.search);
  }, []);
  useEffect(() => {
    let current = true;
    void listProjects().then(async values => {
      if (!current) return;
      setProjects(values);
      const id = new URLSearchParams(location.search).get("project") ?? values.entries[0]?.projectId;
      if (!id) throw new Error("Откройте сохранённое резюме");
      const value = await projectRequest(`/${id}`);
      if (current) { acknowledge(value); setStatus("Сохранено"); }
    }).catch(error => { if (current) setError(error instanceof Error ? error.message : "Не удалось открыть резюме"); });
    return () => { current = false; };
  }, [acknowledge]);
  async function action(work: () => Promise<void>) {
    if (acting.current) return;
    acting.current = true; setBusy(true); setError("");
    try { await work(); }
    catch (error) { setError(error instanceof Error ? error.message : "Не удалось выполнить действие"); }
    finally { acting.current = false; setBusy(false); }
  }
  function open(id: string, reset = false) {
    void action(async () => {
      if (editor.current) await editor.current.flush();
      const next = await projectRequest(`/${id}`);
      if (reset) setReopen(value => value + 1);
      acknowledge(next); setStatus("Сохранено");
    });
  }
  async function saveFile(kind: "archive" | "export") {
    const saved = await editor.current?.flush();
    if (!saved) return;
    acknowledge(saved);
    const blob = await download(saved.workspace.projectId, kind, saved.workspace);
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = kind === "archive" ? "resume.foldcv" : "resume.docx"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main className={`app-shell${collapsed ? " history-collapsed" : ""}`} data-app="foldcv-uir-proof">
    <aside className="history" aria-label="История резюме">
      <div className="brand-row"><span className="brand"><Icon name="fold" />FoldCV<span>.</span></span><button className="icon" aria-label="Свернуть историю" onClick={() => setCollapsed(true)}><Icon name="panel" /></button></div>
      <div className="history-heading"><span className="eyebrow">Ваши резюме</span><span>{projects?.entries.length ?? 0}</span></div>
      <div className="project-list">{projects?.entries.map(item => <div className={`project-item${item.projectId === response?.workspace.projectId ? " active" : ""}`} key={item.projectId}><button className="project-select" disabled={busy} aria-current={item.projectId === response?.workspace.projectId ? "page" : undefined} onClick={() => open(item.projectId)}><strong>{item.title}</strong><small>{item.subtitle}</small></button></div>)}</div>
      <footer className="history-footer"><button disabled={busy || !response} onClick={() => { if (response) open(response.workspace.projectId, true); }}>Открыть заново</button><button disabled={busy || !response} onClick={() => void action(() => saveFile("archive"))}><Icon name="download" />Сохранить .foldcv</button></footer>
    </aside>
    <section className="main-area">
      <header className="app-header"><button className="icon show-history" hidden={!collapsed} aria-label="Развернуть историю" onClick={() => setCollapsed(false)}><Icon name="panel" /></button>
        <div className="project-heading"><span>{response?.identity?.subtitle}</span><h1>{response?.identity?.title ?? "Резюме"}</h1></div>
        <div className="header-actions"><span className="session-status"><span className="dot" />{status}</span><button className="button quiet" disabled={busy || !response} onClick={() => void action(async () => { const next = await editor.current?.flush(); if (next) acknowledge(await projectRequest(`/${next.workspace.projectId}/save`, "POST", {})); })}><Icon name="download" /><span>Сохранить</span></button><button className="button primary" disabled={busy || !response} onClick={() => void action(() => saveFile("export"))}>Экспорт DOCX<Icon name="arrow" /></button></div>
      </header>
      <div className="screen uir-proof-screen">{error && <p role="alert" className="notice error">{error}</p>}
        {response?.workspace.project && <RichEditor key={`${response.workspace.projectId}:${reopen}`} initial={response} acknowledge={acknowledge} onStatus={setStatus} ref={editor} appearance="prototype" portalHost={portalHost} />}
      </div>
    </section>
  </main>;
}

const root = document.getElementById("root");
if (!root) throw new Error("Root is missing");
try { await exchangeSession(); createRoot(root).render(<Proof />); }
catch { createRoot(root).render(<p role="alert">Откройте приложение по адресу из запуска сервиса.</p>); }
