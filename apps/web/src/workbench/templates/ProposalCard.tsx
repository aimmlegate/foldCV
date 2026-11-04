import { lazy, Suspense, useEffect, useState } from "react";
import { proposalCard, type TemplateProposal } from "../../assistant/template";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";

const ProposalDiff = lazy(() => import("./ProposalDiff"));

/** One template proposal: what it changes, where it goes, and Apply, Replace or Discard. The comparison reads the
 * editor text once, when it is opened, and only on the proposal's target; elsewhere it shows the proposed text. */
export function TemplateProposalCard({ value, target, onTarget, current, busy, applying, changed, apply, replace, discard }: {
  value: TemplateProposal; target: string; onTarget: boolean; current: () => string; busy: boolean; applying: boolean; changed: boolean;
  apply: () => void; replace: () => void; discard: () => void;
}) {
  const card = proposalCard(value, changed, busy);
  const [base, setBase] = useState<string | null>(null);
  useEffect(() => { setBase(shown => shown === null ? null : onTarget ? current() : ""); }, [onTarget]);
  return <article className="chat-proposal template-proposal" data-state={value.state} aria-label={`Предложение: ${target}`}>
    <h3>{card.heading}</h3>
    {value.summary && <p>{value.summary}</p>}
    <p className="template-proposal-target">Куда: {target}</p>
    <details className="chat-proposal-change" onToggle={event => setBase(event.currentTarget.open ? onTarget ? current() : "" : null)}>
      <summary>{onTarget ? "Изменения относительно текста в редакторе" : "Текст предложения"}</summary>
      {base !== null && <Suspense fallback={<OperationStatus label="Загружаем сравнение" />}><ProposalDiff original={base} modified={value.text} /></Suspense>}
    </details>
    {card.notice && <p role="status">{card.notice}</p>}
    {value.state === "proposed" && <div className="chat-proposal-actions">
      {changed ? <Button variant="primary" className="small" busy={applying} busyLabel="Заменяем…" disabled={!card.replace} onClick={replace}>Заменить</Button>
        : <Button variant="primary" className="small" busy={applying} busyLabel="Применяем…" disabled={!card.apply} onClick={apply}>Применить</Button>}
      <button type="button" className="text-button" disabled={!card.discard} onClick={discard}>Отклонить</button>
    </div>}
  </article>;
}
