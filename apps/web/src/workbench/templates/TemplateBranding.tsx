import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../../errors/messages";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { OperationStatus } from "../ui/OperationStatus";
import { readTemplateBranding, saveTemplateBranding, type TemplateBranding as Branding, type TemplateConfigState } from "./config";

const TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 2 * 1024 * 1024;
type Pending = { url: string; base64: string } | "remove" | null;

/** A template's own logo in its logo place and an optional footer email (D145). A save is the template's next version,
 * which new imports take; it starts from the saved text, so unsaved YAML edits come first. */
export function TemplateBranding({ templateId, packageHash, blocked, disabled, saved }: {
  templateId: string; packageHash: string; blocked: boolean; disabled: boolean; saved: (state: TemplateConfigState) => void;
}) {
  const [current, setCurrent] = useState<Branding | null>(null);
  const [logo, setLogo] = useState<Pending>(null), [footer, setFooter] = useState("");
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null), [done, setDone] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  // The version this form saved itself: its reply already holds the branding, so it is not read again.
  const applied = useRef<string | null>(null);
  useEffect(() => {
    if (packageHash === applied.current) return;
    let alive = true;
    setCurrent(null); setLogo(null); setProblem(null); setDone(null);
    readTemplateBranding(templateId).then(value => { if (alive) { setCurrent(value); setFooter(value.footer); } })
      .catch((error: unknown) => { if (alive) setProblem(errorMessage(error)); });
    return () => { alive = false; };
  }, [templateId, packageHash]);

  function choose(file: File | undefined) {
    if (!file) return;
    setProblem(null); setDone(null);
    if (!TYPES.includes(file.type)) { setProblem("Нужна картинка PNG, JPEG или WebP."); return; }
    if (file.size > MAX_BYTES) { setProblem("Файл логотипа больше 2 МБ."); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const url = typeof reader.result === "string" ? reader.result : "";
      setLogo({ url, base64: url.slice(url.indexOf(",") + 1) });
    };
    reader.onerror = () => setProblem("Файл не прочитался.");
    reader.readAsDataURL(file);
  }
  async function save() {
    if (!current) return;
    setWorking(true); setProblem(null); setDone(null);
    try {
      const change = { footer: footer.trim(), ...(logo === "remove" ? { removeLogo: true } : logo ? { logo: logo.base64 } : {}) };
      const result = await saveTemplateBranding(templateId, change);
      if (!result.saved) { setProblem(result.error.message); return; }
      applied.current = result.state.package.packageHash;
      setCurrent(result.branding); setFooter(result.branding.footer); setLogo(null);
      setDone(`Сохранено как версия ${result.state.package.revision}. Новые резюме получат логотип и email; готовые не изменятся.`);
      saved(result.state);
    } catch (error) { setProblem(errorMessage(error)); }
    finally { setWorking(false); }
  }

  const busy = working || disabled;
  const shown = logo === "remove" ? null : logo?.url ?? current?.logo ?? null;
  const changed = logo !== null || footer.trim() !== (current?.footer ?? "");
  return <section className="template-branding" aria-label="Логотип и подвал">
    <h4>Логотип и подвал</h4>
    {current === null && problem === null && <OperationStatus label="Загружаем" />}
    {current && <div className="template-branding-fields">
      {current.logoPlace ? <div className="template-logo">
        <div className="template-logo-preview">{shown ? <img src={shown} alt="Логотип шаблона" /> : <span>Без логотипа</span>}</div>
        <div className="template-logo-actions">
          <Button className="small" disabled={busy} onClick={() => input.current?.click()}><Icon name="upload" />{shown ? "Заменить" : "Загрузить логотип"}</Button>
          {shown && <Button className="small" variant="quiet" disabled={busy} onClick={() => { setDone(null); setLogo(current.logo ? "remove" : null); }}>Убрать</Button>}
          <small>PNG, JPEG или WebP до 2 МБ. Без логотипа его место в шапке остаётся пустым.</small>
        </div>
        <input ref={input} hidden type="file" accept={TYPES.join(",")} aria-label="Файл логотипа" disabled={busy}
          onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; choose(file); }} />
      </div> : <small>В этом шаблоне нет места для логотипа.</small>}
      <label htmlFor="template-footer-email">Email в подвале</label>
      <input id="template-footer-email" type="email" value={footer} placeholder="hr@company.com" maxLength={254} disabled={busy}
        onChange={event => { setFooter(event.currentTarget.value); setDone(null); }} />
      <small>Необязательно. Печатается внизу каждой страницы DOCX и PDF.</small>
    </div>}
    {blocked && <small>Сначала сохраните или отмените правки YAML.</small>}
    {problem && <p className="notice error" role="alert">{problem}</p>}
    {done && <OperationStatus state="success" label={done} />}
    {current && <Button className="small" variant="primary" busy={working} busyLabel="Сохраняем…" disabled={!changed || busy || blocked}
      onClick={() => void save()}>Сохранить логотип и email</Button>}
  </section>;
}
