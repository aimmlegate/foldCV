import { Icon } from "../ui/Icon";

/** The mark «Не на странице» of a fact the page does not show, and its always visible way back (D179, sketch A1). */
export function OffPage({ name, busy, restore }: { name: string; busy: boolean; restore: () => void }) {
  return <p className="fact-off-page"><span><Icon name="info" />Не на странице</span>
    <button type="button" className="text-button" disabled={busy} aria-label={`Вернуть на страницу: ${name}`} onClick={restore}>Вернуть на страницу</button></p>;
}
