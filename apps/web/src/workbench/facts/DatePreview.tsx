import { errorMessage } from "../../errors/messages";
import type { DateCascadeProposal } from "../../contracts/generated/date_cascade_proposal";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";

export function DatePreview({ proposal, job, reason, busy, error, close, apply, returnFocus }: {
  proposal: DateCascadeProposal; job: (id: string) => string; reason: string; busy: boolean; error: string; close: () => void; apply: () => void; returnFocus: HTMLElement | null;
}) {
  return <Dialog open title="Проверить даты" returnFocus={returnFocus} close={() => { if (!busy) close(); }}>
    {proposal.status === "available" ? <><p className="dialog-copy">Параллельная работа допустима. Если это ошибка, проверьте предлагаемый сдвиг.</p>
      {proposal.shifts.map(shift => <div key={shift.periodId}>
        <div className="timeline-pair"><div><small>Сейчас</small><strong>{job(shift.jobId)}</strong><p>{shift.before.start.rawText} — {shift.before.end.rawText}</p></div>
          <div><small>После сдвига</small><strong>{job(shift.jobId)}</strong><p>{shift.after.start.rawText} — {shift.after.end.rawText}</p></div></div>
        <p className="dialog-subtitle">Длительность периода сохранена: {shift.inclusiveSpan} {shift.unit === "month" ? "мес." : "дн."}</p>
      </div>)}
      <p className="dialog-subtitle">После сдвига предупреждений: {proposal.warnings.length}</p></> : <p className="dialog-copy">{errorMessage(reason)}</p>}
    <div className="notice warning">Редактирование и экспорт доступны при любом решении.</div>
    {error && <p className="notice warning" role="alert">{errorMessage(error)}</p>}
    <div className="dialog-actions"><button type="button" className="text-button" disabled={busy} onClick={close}>Оставить даты</button>
      {proposal.status === "available" && <Button variant="primary" busy={busy} busyLabel="Сохраняем даты…" onClick={apply}>Изменить даты</Button>}</div>
  </Dialog>;
}
