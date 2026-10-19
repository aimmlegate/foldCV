import { useRef, useState } from "react";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import type { WriterMode } from "../../background/writer";
import { Button } from "../ui/Button";
import { NotificationSection } from "../ui/NotificationCenter";
import { noticeText } from "../ui/notice-text";
import { Spinner } from "../ui/OperationStatus";
import { editorNoticeState } from "./notices";

export function EditorNotices({ mode, localDraft, resolveDraft, warning, clearWarning, syncRecords, resolve, retry, dismiss, report, onOpen }: {
  mode: WriterMode | null; localDraft: boolean; resolveDraft: (choice: "draft" | "saved") => Promise<void>;
  warning: string; clearWarning: () => void; syncRecords: RichProjectResponse["workspace"]["syncRecords"];
  resolve: (id: string) => Promise<void>; retry: (id: string) => Promise<void>; dismiss: (id: string) => Promise<void>; report: (message: string) => void;
  onOpen: () => void;
}) {
  const [resolving, setResolving] = useState(false);
  const [recoveryChoice, setRecoveryChoice] = useState<"draft" | "saved" | null>(null);
  const [pending, setPending] = useState<ReadonlyMap<string, string>>(new Map());
  const running = useRef(new Map<string, string>());
  const { records, recovery, count } = editorNoticeState(mode, warning, syncRecords);
  async function recover(choice: "draft" | "saved") {
    if (resolving) return;
    setResolving(true); setRecoveryChoice(choice);
    try { await resolveDraft(choice); }
    catch (error) { report(error instanceof Error ? error.message : "DRAFT_RECOVERY_FAILED"); }
    finally { setResolving(false); setRecoveryChoice(null); }
  }
  async function attempt(id: string, action: string, work: () => Promise<void>) {
    if (running.current.has(id)) return;
    running.current.set(id, action); setPending(new Map(running.current));
    try { await work(); }
    catch (error) { report(error instanceof Error ? error.message : "Не удалось завершить действие."); }
    finally { running.current.delete(id); setPending(new Map(running.current)); }
  }
  return <NotificationSection count={count} onOpen={onOpen}>
    {recovery && <section className="notice-group" aria-label="Восстановление"><h3>Восстановление</h3>
      <div className="recovery-card" aria-busy={resolving}>
        <p role="alert">{mode === "read_only" ? "Не удалось восстановить редактор. Редактирование приостановлено. Выберите состояние для продолжения."
          : "Ввод сохранён в отдельном черновике. Сначала выберите, какое состояние продолжить."}</p>
        {(mode === "recovering" || localDraft) && <Button variant="primary" disabled={resolving} busy={resolving && recoveryChoice === "draft"} busyLabel="Восстанавливаем…" onClick={() => void recover("draft")}>Использовать мой черновик</Button>}
        <Button variant="quiet" disabled={resolving} busy={resolving && recoveryChoice === "saved"} busyLabel="Открываем…" onClick={() => void recover("saved")}>Продолжить с сохранённого состояния</Button>
        <p className="recovery-disclosure">Продолжение с сохранённого состояния удалит доступный черновик. Невосстановленные правки могут быть потеряны.</p>
      </div>
    </section>}
    {(warning || records.length > 0) && <section className="notice-group" aria-label="Замечания"><h3>Замечания</h3>
      {warning && <p role="alert" className="notice warning">{noticeText(warning)}<button className="text-button" onClick={clearWarning}>Закрыть</button></p>}
      {records.map(record => <div key={record.id} className="notice warning" role="status">
        <p>{record.status === "pending" && !record.errorCode && <Spinner />}{record.status === "failed" ? "Не удалось проверить изменения. Повторите проверку." : record.status === "conflict" ? "Есть другие упоминания. Проверьте связанные факты."
          : record.status === "stale" ? "Предложение устарело. Ваши изменения сохранены." : record.errorCode === "OPERATION_INTERRUPTED" ? "Синхронизация была прервана." : "Синхронизация…"}</p>
        {record.status === "conflict" && <Button variant="quiet" disabled={pending.has(record.id)} busy={pending.get(record.id) === "resolve"} busyLabel="Обновляем…" onClick={() => void attempt(record.id, "resolve", () => resolve(record.id))}>Обновить связанные поля</Button>}
        <Button variant="quiet" disabled={pending.has(record.id)} busy={pending.get(record.id) === "retry"} busyLabel="Проверяем…" onClick={() => void attempt(record.id, "retry", () => retry(record.id))}>Повторить</Button>
        <Button variant="quiet" disabled={pending.has(record.id)} busy={pending.get(record.id) === "dismiss"} busyLabel="Закрываем…" onClick={() => void attempt(record.id, "dismiss", () => dismiss(record.id))}>Закрыть</Button>
      </div>)}
    </section>}
  </NotificationSection>;
}
