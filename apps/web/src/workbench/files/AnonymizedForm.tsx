import { useEffect, useState } from "react";
import type { AnonymizedPreviewV1 } from "../../contracts/generated/contracts";
import { errorMessage } from "../../errors/messages";
import { OperationStatus } from "../ui/OperationStatus";

/** The places to check, as the dialog says them: at most five quotes, then «и ещё N» (A2-d). */
export function checkLine(quotes: readonly string[]): string {
  const unique = [...new Set(quotes)];
  const shown = unique.slice(0, 5).map(quote => `«${quote}»`).join(", ");
  return unique.length ? `Проверьте текст: ${shown}${unique.length > 5 ? ` и ещё ${unique.length - 5}` : ""}` : "";
}

/** The anonymized export's form (D186): the short name to show, what is left out and the places to check. Python makes
 * every value; the form only edits the name. */
export function AnonymizedForm({ load, name, change, busy, initial = null }: {
  load: () => Promise<AnonymizedPreviewV1>; name: string | null; change: (value: string) => void; busy: boolean;
  /** Python's answer when it is already known. */
  initial?: AnonymizedPreviewV1 | null;
}) {
  const [shown, setShown] = useState<AnonymizedPreviewV1 | null>(initial), [failure, setFailure] = useState<unknown>(null);
  useEffect(() => {
    if (initial) return;
    let live = true;
    load().then(value => { if (!live) return; setShown(value); if (name === null) change(value.name); }, error => { if (live) setFailure(error); });
    return () => { live = false; };
  }, []); // Once per dialog: the name the user types is not sent back for a new proposal.
  if (failure !== null) return <p className="notice error" role="alert">{errorMessage(failure)}</p>;
  if (!shown) return <OperationStatus label="Готовим обезличенное резюме" />;
  const notice = checkLine(shown.notices.map(item => item.quote));
  return <div className="anonymized-form">
    <label htmlFor="anonymized-name">Имя в резюме</label>
    <input id="anonymized-name" value={name ?? ""} maxLength={200} disabled={busy} placeholder="Без имени"
      onChange={event => change(event.currentTarget.value)} />
    <p className="anonymized-left-out">{shown.leftOut}</p>
    {notice && <p className="anonymized-check" role="status">{notice}</p>}
  </div>;
}
