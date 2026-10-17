import { useState } from "react";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import type { WriterMode } from "../../background/writer";
import { Button } from "../ui/Button";
import { NoticePanel } from "../ui/NoticePanel";
import { noticeText } from "../ui/notice-text";

export function EditorNotices({ mode, localDraft, resolveDraft, warning, clearWarning, syncRecords, resolve, retry, dismiss, report }: {
  mode: WriterMode | null; localDraft: boolean; resolveDraft: (choice: "draft" | "saved") => Promise<void>;
  warning: string; clearWarning: () => void; syncRecords: RichProjectResponse["workspace"]["syncRecords"];
  resolve: (id: string) => Promise<void>; retry: (id: string) => Promise<void>; dismiss: (id: string) => Promise<void>; report: (message: string) => void;
}) {
  const [resolving, setResolving] = useState(false);
  const records = syncRecords.filter(record => ["failed", "conflict", "pending", "stale"].includes(record.status));
  async function recover(choice: "draft" | "saved") {
    if (resolving) return;
    setResolving(true);
    try { await resolveDraft(choice); }
    catch (error) { report(error instanceof Error ? error.message : "DRAFT_RECOVERY_FAILED"); }
    finally { setResolving(false); }
  }
  const attempt = (work: Promise<void>) => { void work.catch(error => report(error instanceof Error ? error.message : "Не удалось завершить действие.")); };
  return <>
    {(mode === "recovering" || mode === "read_only") && <NoticePanel count={1} label="Восстановление" attention={mode}>
      <div className="recovery-card" aria-busy={resolving}>
        <p role="alert">{mode === "read_only" ? "Не удалось восстановить редактор. Редактирование приостановлено. Выберите состояние для продолжения."
          : "Ввод сохранён в отдельном черновике. Сначала выберите, какое состояние продолжить."}</p>
        {(mode === "recovering" || localDraft) && <Button variant="primary" disabled={resolving} onClick={() => void recover("draft")}>Использовать мой черновик</Button>}
        <Button variant="quiet" disabled={resolving} onClick={() => void recover("saved")}>Продолжить с сохранённого состояния</Button>
        <p className="recovery-disclosure">Продолжение с сохранённого состояния удалит доступный черновик. Невосстановленные правки могут быть потеряны.</p>
      </div>
    </NoticePanel>}
    <NoticePanel count={(warning ? 1 : 0) + records.length} attention={warning}>
      {warning && <p role="alert" className="notice warning">{noticeText(warning)}<button className="text-button" onClick={clearWarning}>Закрыть</button></p>}
      {records.map(record => <div key={record.id} className="notice warning" role="status">
        <p>{record.status === "failed" ? "Не удалось проверить изменения. Повторите проверку." : record.status === "conflict" ? "Есть другие упоминания. Проверьте связанные факты."
          : record.status === "stale" ? "Предложение устарело. Ваши изменения сохранены." : record.errorCode === "OPERATION_INTERRUPTED" ? "Синхронизация была прервана." : "Синхронизация…"}</p>
        {record.status === "conflict" && <button className="text-button" onClick={() => attempt(resolve(record.id))}>Обновить связанные поля</button>}
        <button className="text-button" onClick={() => attempt(retry(record.id))}>Повторить</button>
        <button className="text-button" onClick={() => attempt(dismiss(record.id))}>Закрыть</button>
      </div>)}
    </NoticePanel>
  </>;
}
