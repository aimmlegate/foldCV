import { useEffect, useRef, useState } from "react";
import type { RulesSettings } from "../contracts/generated/rules_settings";
import { ApiFailure, rulesRequest, saveRulesRequest } from "./api";

const errors: Record<string, string> = {
  RULES_PRESETS_REQUIRED: "Нужны оба заголовка: ## Preset: shorten и ## Preset: clarify. Добавьте под каждым непустую инструкцию.",
  RULES_STALE: "Правила изменены в другом окне. Загрузите актуальную версию и сравните её со своим текстом перед сохранением.",
  RULES_TOO_LARGE: "Правила превышают 32 КБ. Сократите текст и повторите сохранение.",
  RULES_INVALID_TEXT: "Проверьте текст правил: он не должен быть пустым или содержать управляющие символы.",
  INVALID_REQUEST: "Правила должны содержать текст и занимать не больше 32 КБ. Сократите текст или заполните пустой редактор.",
};

export function RulesPanel() {
  const [saved, setSaved] = useState<RulesSettings | null>(null), [markdown, setMarkdown] = useState("");
  const [busy, setBusy] = useState(true), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [stale, setStale] = useState(false), [comparison, setComparison] = useState(false);
  const active = useRef(true), draft = useRef(""), epoch = useRef(0);
  function change(text: string) { draft.current = text;setMarkdown(text);setMessage(""); }
  async function load(preserve = false) {
    const captured = ++epoch.current;
    setBusy(true);setError("");
    try {
      const current = await rulesRequest();if (!active.current || captured !== epoch.current) return;
      setSaved(current);setStale(false);setComparison(preserve);
      if (!preserve) change(current.markdown);
      else setMessage("Актуальная версия загружена. Ваш текст остался в редакторе; сравните его с сохранённым ниже.");
    } catch { if (active.current && captured === epoch.current) setError("Не удалось прочитать правила. Повторите загрузку; текст остаётся в редакторе."); }
    finally { if (active.current && captured === epoch.current) setBusy(false); }
  }
  async function save() {
    if (!saved || busy || stale) return;
    const captured = ++epoch.current;
    const submitted = { markdown: draft.current, baseRevision: saved.revision };
    setBusy(true);setError("");setMessage("");
    try {
      const current = await saveRulesRequest(submitted);if (!active.current || captured !== epoch.current) return;
      setSaved(current);setComparison(false);
      if (draft.current === submitted.markdown) { change(current.markdown);setMessage("Правила сохранены. Следующие операции используют новую версию."); }
      else setMessage("Предыдущий текст правил сохранён. В редакторе есть новые несохранённые правки.");
    } catch (failure) {
      if (!active.current || captured !== epoch.current) return;
      const code = failure instanceof ApiFailure ? failure.code : "REQUEST_FAILED";
      setError(errors[code] ?? "Не удалось сохранить правила. Текст остаётся в редакторе; повторите действие.");setStale(code === "RULES_STALE");
    } finally { if (active.current && captured === epoch.current) setBusy(false); }
  }
  useEffect(() => { active.current = true;void load();return () => { active.current = false;++epoch.current; }; }, []);
  const dirty = saved !== null && markdown !== saved.markdown;
  return <section className="next-rules" aria-label="Общие правила">
    <h2>Общие правила и пресеты</h2>
    <p>Редактируйте правила оформления текста и инструкции «Сократить» / «Яснее». Изменения действуют на следующие операции; текущее резюме сохраняется.</p>
    <p>Сохраните заголовки <code>## Preset: shorten</code> и <code>## Preset: clarify</code> с инструкциями под ними.</p>
    {saved && <p>Версия правил: {saved.revision}</p>}
    <label>Markdown правил<textarea aria-label="Markdown правил" rows={16} spellCheck={false} disabled={saved === null}
      value={markdown} onChange={event => change(event.target.value)} /></label>
    <div className="next-settings-controls"><button disabled={!dirty || busy || stale} onClick={() => { void save(); }}>Сохранить правила</button>
      <button disabled={busy} onClick={() => { void load(saved !== null); }}>Загрузить актуальную версию правил</button></div>
    {busy && <p role="status">Читаем или сохраняем правила…</p>}
    {dirty && <p role="status">Есть несохранённые изменения правил.</p>}
    {message && <p role="status">{message}</p>}{error && <p role="alert" className="text-danger">{error}</p>}
    {comparison && saved && <label>Сохранённая версия для сравнения<textarea aria-label="Сохранённая версия правил" rows={8} readOnly value={saved.markdown} /></label>}
  </section>;
}
