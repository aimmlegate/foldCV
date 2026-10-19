import { useRef, useState } from "react";
import type { TimelineReport } from "../../contracts/generated/timeline_report";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { OperationStatus } from "../ui/OperationStatus";

export type FileMode = "open" | "save" | "export";
export function FileDialog({ mode, title, subtitle, filename, timeline, error, busy, operation, close, download, upload }: {
  mode: FileMode; title: string; subtitle: string; filename: string; timeline: TimelineReport | null; error: string; busy: boolean;
  operation?: string | undefined;
  close: () => void; download: () => Promise<boolean>; upload: (file: File) => Promise<boolean>;
}) {
  const input = useRef<HTMLInputElement>(null), [message, setMessage] = useState("");
  const exporting = mode === "export", opening = mode === "open";
  return <Dialog open close={() => { if (!busy) close(); }} title={exporting ? "Экспорт документа" : opening ? "Открыть проект" : "Сохранить проект"}>
    {exporting ? <><p className="dialog-copy">{title}<br />{subtitle}</p>
      <div className="export-format"><span className="format-icon">W</span><div><strong>Документ Word</strong><small>DOCX · редактируемый текст и таблицы</small></div><Icon name="check" /></div>
      <div className="export-summary"><span>Шаблон</span><strong>FoldCV / две колонки</strong></div>
      {(timeline?.warnings.some(warning => warning.kind === "overlap") ?? false) && <p className="notice warning">Проверьте пересекающиеся периоды работы.</p>}
      {timeline === null && <p className="notice">Проверка дат сейчас недоступна. Экспорт доступен.</p>}
    </> : <><p className="dialog-copy">Файл .foldcv хранит исходник, факты и документ.</p>
      <p className="notice">{opening ? "Текущие изменения сохранятся перед открытием." : "Файл .foldcv можно открыть на другом компьютере."}</p>
      <div className="demo-file-row"><span>{opening ? "Файл .foldcv" : filename}</span>
        <Button className="small" busy={busy} busyLabel={opening ? "Открываем…" : "Готовим…"} onClick={() => {
          setMessage("");
          if (opening) input.current?.click();
          else void download().then(done => { if (done) setMessage("Файл передан браузеру для сохранения."); });
        }}><Icon name={opening ? "upload" : "download"} />{opening ? "Открыть .foldcv" : "Скачать .foldcv"}</Button>
      </div>
      {opening && <input ref={input} hidden type="file" aria-label="Открыть файл проекта" accept=".foldcv" disabled={busy} onChange={event => {
        const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
        if (file) void upload(file).then(done => { if (done) close(); });
      }} />}
    </>}
    <div className="operation-slot">{busy ? <OperationStatus label={operation ?? (opening ? "Открываем файл" : "Готовим файл")} timed />
      : error ? <p className="notice error" role="alert">{error}</p> : message ? <OperationStatus state="success" label={message} /> : null}</div>
    <div className="dialog-actions">{exporting ? <><button className="text-button" disabled={busy} onClick={close}>Вернуться к тексту</button>
      <Button variant="primary" busy={busy} busyLabel="Готовим DOCX…" onClick={() => { setMessage(""); void download().then(done => { if (done) setMessage("Документ передан браузеру для сохранения."); }); }}>Скачать DOCX<Icon name="download" /></Button></>
      : <Button disabled={busy} onClick={close}>Закрыть</Button>}
    </div>
  </Dialog>;
}
