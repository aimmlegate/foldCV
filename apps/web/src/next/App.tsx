import { useEffect, useMemo, useRef, useState } from "react";
import { FieldEditor, type FieldEditorHandle } from "./FieldEditor";
import { projectRequest, sourceRequest, errorLabel, type Workspace } from "./api";
import { SourcePanel } from "./SourcePanel";
import type { SourceContext } from "../contracts/generated/source_context";
import { documentFields } from "./fields";
import { useTheme } from "./theme";
import sample from "../../../../tests/fixtures/recovery/E1.txt?raw";

const stageLabels = { extract: "Читаем исходник", normalize_semantics: "Разбираем факты", draft_prose: "Готовим резюме", assemble: "Проверяем и оформляем", render: "Проверяем и оформляем" };
export function App() {
  const theme = useTheme();
  const [text, setText] = useState("");
  const [input, setInput] = useState<"text" | "file">("text");
  const [fileName, setFileName] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [buffered, setBuffered] = useState(false);
  const [slot, setSlot] = useState<string | null>(null);
  const [selectionFingerprint, setSelectionFingerprint] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [source, setSource] = useState<SourceContext | null>(null);
  const sourceEpoch = useRef(0);
  const editor = useRef<FieldEditorHandle>(null);
  const lastSlot = useRef("profile");
  const requestEpoch = useRef(0);
  const chooser = useRef<HTMLInputElement>(null);
  const generation = workspace?.generations.find(item => item.id === generationId);
  const document = workspace?.project?.document;
  const fields = useMemo(() => document ? documentFields(document) : [], [document]);
  const initialArtifact = workspace?.project?.renders.find(render => render.artifactAvailable && render.docx);

  useEffect(() => {
    if (!workspace || !generationId || !generation || !["queued", "running"].includes(generation.status)) return;
    let alive = true;
    const id = workspace.projectId, epoch = requestEpoch.current;
    const timer = window.setTimeout(() => {
      void projectRequest(`/v1/projects/${id}`).then(result => {
        if (alive && epoch === requestEpoch.current) { setWorkspace(result.workspace); setSelectionFingerprint(result.selectionFingerprint ?? null); }
      }).catch(error => { if (alive) setError(errorLabel(error)); });
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [workspace, generationId, generation]);

  async function choose(file: File) {
    const epoch = ++requestEpoch.current;
    setInput("file"); setFileName(file.name); setBusy(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await projectRequest(workspace ? `/v1/projects/${workspace.projectId}/input` : "/v1/projects/input", workspace ? "PUT" : "POST", body);
      if (epoch === requestEpoch.current) { setWorkspace(result.workspace); setSelectionFingerprint(result.selectionFingerprint ?? null); setGenerationId(null); }
    } catch (error) { if (epoch === requestEpoch.current) setError(errorLabel(error)); }
    finally { if (epoch === requestEpoch.current) setBusy(false); }
  }
  async function create() {
    const epoch = ++requestEpoch.current;
    setBusy(true); setError("");
    try {
      const result = await projectRequest(workspace ? `/v1/projects/${workspace.projectId}/generations` : "/v1/projects", "POST",
        input === "text" ? { text } : {});
      if (epoch === requestEpoch.current) { setWorkspace(result.workspace); setSelectionFingerprint(result.selectionFingerprint ?? null); setGenerationId(result.generationId); }
    } catch (error) { setError(errorLabel(error)); }
    finally { setBusy(false); }
  }
  async function control(action: "cancel" | "retry") {
    if (!workspace || !generationId) return;
    setBusy(true); setError("");
    try {
      const result = await projectRequest(`/v1/projects/${workspace.projectId}/generations/${generationId}/${action}`, "POST", {});
      setWorkspace(result.workspace); setGenerationId(result.generationId);
      setSelectionFingerprint(result.selectionFingerprint ?? null);
    } catch (error) { setError(errorLabel(error)); }
    finally { setBusy(false); }
  }
  const running = generation && ["queued", "running"].includes(generation.status);
  const failed = generation && ["failed", "cancelled", "interrupted"].includes(generation.status);
  const usable = input === "text" ? !!text.trim() : !!workspace?.preDraft?.extractedText.trim();
  async function showSource() {
    if (!workspace || !selectionFingerprint) return;
    const captured = editor.current?.capture();
    const first = captured?.spans[0];
    const epoch = ++sourceEpoch.current;
    setSourceOpen(true); setSourceBusy(true); setSource(null);
    try {
      const context = await sourceRequest({ projectId: workspace.projectId, documentRevision: workspace.documentRevision,
        selection: captured && first ? { projectId: workspace.projectId, documentRevision: workspace.documentRevision,
          dependencyFingerprint: selectionFingerprint, spans: [first, ...captured.spans.slice(1)] } : null,
        fieldIds: captured && first ? [] : fields.filter(field => field.slotId === (slot ?? lastSlot.current)).map(field => field.fieldId) });
      if (epoch !== sourceEpoch.current) return;
      setSource(context);
      if (context.status === "stale") {
        const refreshed = await projectRequest(`/v1/projects/${workspace.projectId}`);
        if (epoch === sourceEpoch.current) { setWorkspace(refreshed.workspace); setSelectionFingerprint(refreshed.selectionFingerprint ?? null); }
      }
    } catch (error) { if (epoch === sourceEpoch.current) setError(errorLabel(error)); }
    finally { if (epoch === sourceEpoch.current) setSourceBusy(false); }
  }
  return <main data-app="foldcv-next" className="next-shell">
    <header className="next-header">
      <strong className="next-brand">FoldCV.</strong>
      <button className="next-title" disabled aria-label="Меню проекта">{workspace?.title ?? "Новое резюме"}</button>
      <span className="next-save" role="status">{buffered ? "Правки в текущем окне" : workspace ? "В памяти приложения" : ""}</span>
      <div className="next-actions">
        <button disabled>Сохранить проект</button><button disabled>Экспорт DOCX</button><button disabled>Настройки</button>
        <label className="next-theme">Тема <select aria-label="Тема" value={theme.mode} onChange={event => theme.select(event.target.value)}>
          <option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option>
        </select></label>
      </div>
    </header>
    {error && <p className="next-message text-danger" role="alert">{error}</p>}
    {generation && <section className="next-progress" aria-label="Создание резюме">
      <p role="status">{running ? stageLabels[generation.stages.find(stage => ["queued", "running"].includes(stage.status))?.kind ?? "render"]
        : generation.status === "completed" ? "Резюме готово" : generation.status === "cancelled" ? "Создание отменено" : "Создание не завершено"}</p>
      {running && <button disabled={busy} onClick={() => { void control("cancel"); }}>Отменить создание</button>}
      {failed && <button disabled={busy} onClick={() => { void control("retry"); }}>Повторить создание</button>}
      {generation.stages.some(stage => stage.docxError) && <p role="alert">Документ готов. DOCX пока не удалось оформить; текст доступен для правок.</p>}
      {initialArtifact && workspace && <a className="next-download" download="resume.docx"
        href={`/v1/projects/${workspace.projectId}/renders/${initialArtifact.id}/docx`}>Скачать исходный DOCX</a>}
    </section>}
    {document ? <section className="next-editor-surface" aria-label="Документ">
      <p className="next-editor-note">Текст можно редактировать. Пока правки остаются в текущем окне.</p>
      <div className="next-editor-tools"><button disabled={sourceBusy} onPointerDown={event => event.preventDefault()}
        onClick={() => { void showSource(); }}>Показать исходник</button></div>
      <div className="next-document"><FieldEditor ref={editor} key={workspace?.projectId} fields={fields} theme={theme.resolved} annotations={workspace?.annotations ?? []} callbacks={{
        buffer: () => setBuffered(true), selection: () => {}, slot: value => { setSlot(value); if (value) lastSlot.current = value; }, departure: () => {},
        restore: () => setError("Восстановление правок пока недоступно."),
      }} /></div>
      <p className="next-editor-status" aria-live="polite">{slot ? "Редактирование текста" : ""}</p>
    </section> : <section className="next-start">
      <div className="next-intro"><p className="next-eyebrow">ХОРОШИЙ ТЕКСТ НАЧИНАЕТСЯ С ФАКТОВ</p>
        <h1>Дайте резюме<br />чистый лист.</h1><p>Добавьте исходник. Получите полный документ<br />для окончательных правок.</p></div>
      <div className="next-input">
        <div className="next-upload" onDragOver={event => event.preventDefault()} onDrop={event => {
          event.preventDefault(); const file = event.dataTransfer.files[0]; if (file && !busy && !running) void choose(file);
        }}>
          <h2>Начните с резюме</h2><p>PDF, DOCX, TXT, Markdown</p>
          <button disabled={busy || !!running} onClick={() => chooser.current?.click()}>Выбрать файл</button>
          <input ref={chooser} type="file" accept=".pdf,.docx,.txt,.md,.markdown" aria-label="Файл резюме" hidden onChange={event => {
            const file = event.target.files?.[0]; if (file) void choose(file); event.target.value = "";
          }} />
        </div>
        <button className="next-sample" disabled={busy || !!running} onClick={() => { setText(sample); setInput("text"); }}>Открыть пример</button>
        <label className="next-paste-label" htmlFor="resume-input">Или вставьте текст</label>
        <textarea id="resume-input" rows={8} maxLength={60000} disabled={busy || !!running}
          value={input === "file" ? workspace?.preDraft?.extractedText ?? "" : text}
          onChange={event => { setText(event.target.value); setInput("text"); }} />
        <p className="next-selected">Выбрано: {input === "file" ? fileName : "вставленный текст"}</p>
        {workspace?.preDraft?.warnings.length ? <p className="next-warning" role="status">{usable
          ? "Часть содержимого не удалось прочитать. Доступный текст сохранён в памяти."
          : "Доступного текста нет. Выберите другой файл или вставьте текст."}</p> : null}
        <p className="next-disclosure">При создании выбранный текст передаётся настроенной модели через CLI.</p>
        <button className="next-create" disabled={!usable || busy || !!running} onClick={() => { void create(); }}>{busy ? "Читаем исходник…" : "Создать резюме"}</button>
      </div>
    </section>}
    {sourceOpen && workspace && <SourcePanel context={source} workspace={workspace} loading={sourceBusy}
      close={() => { ++sourceEpoch.current; setSourceOpen(false); setSourceBusy(false); }} />}
  </main>;
}
