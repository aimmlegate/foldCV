import { lazy, Suspense, useState } from "react";
import { proposalCard, type TemplateProposal } from "../../assistant/template";
import { Button } from "../ui/Button";
import { OperationStatus } from "../ui/OperationStatus";

const ProposalDiff = lazy(() => import("./ProposalDiff"));

/** One template proposal: what it changes, where it goes, and Apply, Replace or Discard. */
export function TemplateProposalCard({ value, target, current, busy, applying, changed, apply, replace, discard }: {
  value: TemplateProposal; target: string; current: string; busy: boolean; applying: boolean; changed: boolean;
  apply: () => void; replace: () => void; discard: () => void;
}) {
  const card = proposalCard(value, changed, busy);
  const [diff, setDiff] = useState(false);
  return <article className="chat-proposal template-proposal" data-state={value.state} aria-label={`Предложение: ${target}`}>
    <h3>{card.heading}</h3>
    {value.summary && <p>{value.summary}</p>}
    <p className="template-proposal-target">Куда: {target}</p>
    <details className="chat-proposal-change" onToggle={event => setDiff(event.currentTarget.open)}>
      <summary>Изменения относительно текста в редакторе</summary>
      {diff && <Suspense fallback={<OperationStatus label="Загружаем сравнение" />}><ProposalDiff original={current} modified={value.text} /></Suspense>}
    </details>
    {card.notice && <p role="status">{card.notice}</p>}
    {value.state === "proposed" && <div className="chat-proposal-actions">
      {changed ? <Button variant="primary" className="small" busy={applying} busyLabel="Заменяем…" disabled={!card.replace} onClick={replace}>Заменить</Button>
        : <Button variant="primary" className="small" busy={applying} busyLabel="Применяем…" disabled={!card.apply} onClick={apply}>Применить</Button>}
      <button type="button" className="text-button" disabled={!card.discard} onClick={discard}>Отклонить</button>
    </div>}
  </article>;
}
