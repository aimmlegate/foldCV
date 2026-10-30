import { useEffect, useMemo, useRef, useState } from "react";
import type { FocusIconChoices } from "../../projects/api";
import type { PanelCommand } from "../../rich/v7-panel";
import { searchIcons } from "../../rich/v7-focus";
import { assetUrl } from "../../rich/v7-presentation";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/OperationStatus";
import { errorMessage } from "../../errors/messages";
import { factError } from "./error";
import type { FocusEntry } from "./FocusYears";

/** `id` is what a click saves: an icon, or "" for the template's own choice, whose `url` is null when it shows none. */
type Option = { id: string; label: string; url: string | null; icon: string };

/** A Focus row's icon from its template's icons (D122), found by name: the whole list is never shown. The choice is
 * saved with the document and given to rows of the same technology added later. */
export function FocusIconDialog({ entry, load, submit, close }: { entry: FocusEntry; load: () => Promise<FocusIconChoices>;
  submit: (command: PanelCommand) => Promise<void>; close: () => void }) {
  const [choices, setChoices] = useState<FocusIconChoices | null>(null), [failed, setFailed] = useState("");
  const [query, setQuery] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  // After the dialog opens: an autofocus on mount runs before showModal, which then focuses the close button.
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    let live = true;
    load().then(value => { if (live) setChoices(value); },
      (reason: unknown) => { if (live) setFailed(errorMessage(reason, "Не удалось загрузить иконки. Закройте окно и откройте его снова.")); });
    return () => { live = false; };
  }, [load]);
  const found = useMemo(() => choices ? searchIcons(choices.icons, query) : [], [choices, query]);
  const current = entry.icon?.id ?? null;
  // With an empty search: the template's own icon to return to and the one remembered for this name.
  const suggestions = useMemo(() => {
    const row = choices?.rows.get(entry.recordId), result: Option[] = [];
    if (!row) return result;
    if (entry.chosen) result.push(row.automatic ? { id: "", label: "Как в шаблоне", url: assetUrl(row.automatic), icon: row.automatic.id }
      : { id: "", label: "Без иконки", url: null, icon: "" });
    const remembered = row.remembered ? choices?.icons.find(icon => icon.id === row.remembered) : undefined;
    if (remembered && remembered.id !== current)
      result.push({ id: remembered.id, label: "Выбранная раньше", url: assetUrl(remembered), icon: remembered.id });
    return result;
  }, [choices, entry.recordId, entry.chosen, current]);
  async function choose(icon: string) {
    if (busy) return;
    if (icon === (entry.chosen ? current : "")) { close(); return; }
    setBusy(true); setError("");
    try { await submit({ operation: "set_focus_icon", recordId: entry.recordId, values: { icon } }); close(); }
    catch (reason) { setError(factError(reason)); }
    finally { setBusy(false); }
  }
  const options: Option[] = query.trim() ? found.map(icon => ({ id: icon.id, label: icon.label, url: assetUrl(icon), icon: icon.id })) : suggestions;
  return <Dialog open close={() => { if (!busy) close(); }} title={`Иконка: ${entry.display}`}>
    <form className="focus-icon-search" onSubmit={event => { event.preventDefault(); if (options[0]) void choose(options[0].id); }}>
      <input ref={input} type="search" aria-label="Найти иконку" placeholder="Например: postgres, react, docker" value={query}
        disabled={busy} onChange={event => setQuery(event.target.value)} />
    </form>
    {!choices && !failed && <p className="dialog-copy"><Spinner /> Загружаем иконки шаблона…</p>}
    {failed && <p className="notice warning" role="alert">{failed}</p>}
    {choices && <>
      {options.length > 0 && <div className="focus-icon-grid" role="group" aria-label={query.trim() ? "Найденные иконки" : "Подсказки"}>
        {options.map(option => <button key={option.id || "template"} type="button" disabled={busy}
          title={option.label === option.icon || !option.icon ? option.label : `${option.label} — ${option.icon}`}
          aria-pressed={option.id === (entry.chosen ? current : "")} onClick={() => { void choose(option.id); }}>
          {option.url ? <img src={option.url} alt="" loading="lazy" /> : <span className="focus-icon-empty" aria-hidden="true" />}
          <span>{option.label}</span>
        </button>)}
      </div>}
      <p className="dialog-copy">{query.trim() ? found.length ? "Enter выбирает первую." : "Ничего не нашлось. Иконки есть не для всех технологий."
        : "Введите название технологии: покажем подходящие иконки."}</p>
      <p className="dialog-copy">Выбор запомнится: эта технология получит ту же иконку и в следующих резюме.</p>
    </>}
    {error && <p className="notice warning" role="alert">{error}</p>}
    <div className="dialog-actions"><Button disabled={busy} onClick={close}>{busy ? "Сохраняем…" : "Закрыть"}</Button></div>
  </Dialog>;
}
