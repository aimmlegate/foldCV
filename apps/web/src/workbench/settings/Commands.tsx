import { useState } from "react";
import { errorMessage } from "../../errors/messages";
import { Button } from "../ui/Button";
import type { SettingsDrafts, SettingsState } from "./drafts";
import { commandsProblem, mergeCommands, presetBodies, withPresetBody, type PresetKey } from "./presets";
import { RowState, SettingsGroup } from "./Rows";

const fields: readonly { key: PresetKey; label: string; hint: string }[] = [
  { key: "shorten", label: "Сократить", hint: "Что делает команда «Сократить» в правке текста." },
  { key: "clarify", label: "Сделать яснее", hint: "Что делает команда «Сделать яснее»." }];
const bodies = (markdown: string): Record<PresetKey, string> => {
  const { shorten, clarify } = presetBodies(markdown);
  return { shorten: shorten ?? "", clarify: clarify ?? "" };
};

/** Settings → Команды (D147): the two commands as two fields. The Markdown with the preset headings is assembled
 * here and text outside them keeps every byte. Saved on its own from the bar that shows while the text differs. */
export function CommandsSettings({ state, controller }: { state: SettingsState; controller: SettingsDrafts }) {
  const markdown = state.draft.markdown;
  // The fields keep what was typed, trailing spaces too; a text from elsewhere (load, save, cancel) fills them anew.
  const [values, setValues] = useState(() => bodies(markdown)), [made, setMade] = useState(markdown);
  if (markdown !== made) { setMade(markdown); setValues(bodies(markdown)); }
  const edit = (key: PresetKey, value: string) => {
    const produced = withPresetBody(markdown, key, value);
    setValues({ ...values, [key]: value }); setMade(produced); controller.change("markdown", produced);
  };
  const dirty = controller.dirty.includes("rules"), saving = state.pending.includes("rules");
  const problem = commandsProblem(markdown, values);
  const refused = state.rules && state.errors.rules && !state.staleRules ? errorMessage(state.errors.rules) : null;
  return <>
    <SettingsGroup>
      {fields.map(field => <div className="settings-field" key={field.key}>
        <label htmlFor={`rules-${field.key}`}>{field.label}</label><p>{field.hint}</p>
        <textarea className="rules-text" id={`rules-${field.key}`} spellCheck={false} rows={5} disabled={!state.rules}
          value={values[field.key]} onChange={event => edit(field.key, event.currentTarget.value)} />
      </div>)}
    </SettingsGroup>
    <div className="commands-saved"><RowState pending={saving && !dirty} at={state.marks.markdown} /></div>
    {state.staleRules && <p className="notice warning" role="status">Команды изменились в другом окне. Загрузите сохранённую версию: ваши правки
      останутся в полях. <button type="button" className="text-button" disabled={state.loading || state.saving} onClick={() => void controller.reloadRules(mergeCommands)}>
        Загрузить сохранённую версию</button></p>}
    {state.comparison && state.rules && <details className="commands-saved-version"><summary>Сохранённая версия</summary>
      <textarea className="rules-text" aria-label="Сохранённая версия команд" readOnly value={state.rules.markdown} /></details>}
    {(dirty || saving) && <div className="settings-savebar" role="region" aria-label="Несохранённые команды">
      <span className={problem || refused ? "settings-savebar-error" : undefined} role="status">{problem ?? refused ?? "Не сохранено"}</span>
      <Button variant="quiet" disabled={saving} onClick={() => controller.revertRules()}>Отмена</Button>
      <Button variant="primary" busy={saving} busyLabel="Сохраняем…" disabled={problem !== null || state.loading}
        onClick={() => void controller.saveRules()}>Сохранить</Button>
    </div>}
  </>;
}
