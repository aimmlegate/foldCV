import { errorMessage } from "../../errors/messages";
import { useRef, useState } from "react";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { OperationStatus } from "../ui/OperationStatus";
import { deliveryMessage, type Delivery } from "./delivery";
import { printHint, printPlatform } from "./print";

export type FileMode = "open" | "save" | "export";
type ExportFormat = "docx" | "pdf";
export function FileDialog({ mode, title, subtitle, filename, error, busy, operation, close, download, print, upload, templateName }: {
  mode: FileMode; title: string; subtitle: string; filename: string; error: string; busy: boolean;
  /** The project's own captured template. */
  templateName?: string | undefined;
  operation?: string | undefined;
  close: () => void; download: () => Promise<Delivery | null>; upload: (file: File) => Promise<boolean>;
  /** PDF export through the system print window; true once the window was asked to open. */
  print: () => Promise<boolean>;
}) {
  const input = useRef<HTMLInputElement>(null), [message, setMessage] = useState(""), [format, setFormat] = useState<ExportFormat>("docx");
  const exporting = mode === "export", opening = mode === "open", pdf = exporting && format === "pdf";
  const choose = (value: ExportFormat) => { setFormat(value); setMessage(""); };
  return <Dialog open close={() => { if (!busy) close(); }} title={exporting ? "Экспорт" : opening ? "Открыть файл" : "Сохранить в файл"}>
    {exporting ? <><p className="dialog-copy">{title}<br />{subtitle}</p>
      <div className="export-formats" role="radiogroup" aria-label="Формат">
        <FormatOption value="docx" mark="W" label="DOCX" detail="Для Word и Google Docs" chosen={format} busy={busy} choose={choose} />
        <FormatOption value="pdf" mark="PDF" label="PDF" detail="Через окно печати, как резюме на экране" chosen={format} busy={busy} choose={choose} />
      </div>
      <div className="export-summary"><span>Шаблон</span><strong>{templateName ?? "FoldCV / две колонки"}</strong></div>
    </> : <>{opening && <p className="notice">Текущие изменения сохранятся.</p>}
      <div className="demo-file-row"><span>{opening ? "Файл .foldcv" : filename}</span>
        <Button className="small" busy={busy} busyLabel={opening ? "Открываем…" : "Готовим…"} onClick={() => {
          setMessage("");
          if (opening) input.current?.click();
          else void download().then(delivery => setMessage(deliveryMessage(delivery)));
        }}><Icon name={opening ? "upload" : "download"} />{opening ? "Открыть .foldcv" : "Скачать .foldcv"}</Button>
      </div>
      {opening && <input ref={input} hidden type="file" aria-label="Файл .foldcv" accept=".foldcv" disabled={busy} onChange={event => {
        const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
        if (file) void upload(file).then(done => { if (done) close(); });
      }} />}
    </>}
    <div className="operation-slot">{busy ? <OperationStatus label={operation ?? (opening ? "Открываем файл" : "Готовим файл")} timed />
      : error ? <p className="notice error" role="alert">{errorMessage(error)}</p> : message ? <OperationStatus state="success" label={message} />
      : pdf ? <p className="print-hint">{printHint(printPlatform())}</p> : null}</div>
    <div className="dialog-actions">{exporting ? <><button className="text-button" disabled={busy} onClick={close}>{message ? "Закрыть" : "Отмена"}</button>
      {pdf ? <Button variant="primary" busy={busy} busyLabel="Открываем печать…" onClick={() => { void print().then(done => { if (done) close(); }); }}>Печать в PDF<Icon name="arrow" /></Button>
        : <Button variant="primary" busy={busy} busyLabel="Готовим DOCX…" onClick={() => { setMessage(""); void download().then(delivery => setMessage(deliveryMessage(delivery))); }}>Скачать DOCX<Icon name="download" /></Button>}</>
      : <Button disabled={busy} onClick={close}>Закрыть</Button>}
    </div>
  </Dialog>;
}

function FormatOption({ value, mark, label, detail, chosen, busy, choose }: {
  value: ExportFormat; mark: string; label: string; detail: string; chosen: ExportFormat; busy: boolean; choose: (value: ExportFormat) => void;
}) {
  return <label className="export-format">
    <input className="sr-only" type="radio" name="export-format" value={value} checked={chosen === value} disabled={busy} onChange={() => choose(value)} />
    <span className="format-icon" aria-hidden="true">{mark}</span>
    <span><strong>{label}</strong><small>{detail}</small></span>
    {chosen === value && <Icon name="check" />}
  </label>;
}
