import { Icon } from "../ui/Icon";

/** The eye of a job or a résumé block in Facts (D185): pressed while the block is off the page. Python's plan says the
 * state; the press sends hide or show. */
export function HideEye({ name, hidden, disabled, toggle }: { name: string; hidden: boolean; disabled: boolean; toggle: () => void }) {
  const label = `${hidden ? "Показать" : "Скрыть"}: ${name}`;
  return <button type="button" className="icon fact-eye" aria-pressed={hidden} aria-label={label} title={hidden ? "Показать" : "Скрыть"}
    disabled={disabled} onClick={toggle}><Icon name={hidden ? "eye-off" : "eye"} /></button>;
}

/** The small mark of a hidden row: the crossed eye and «Скрыто», no box. */
export function HiddenMark() {
  return <small className="fact-hidden-mark"><Icon name="eye-off" />Скрыто</small>;
}
