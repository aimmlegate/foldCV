import { useState } from "react";
import type { useEdits } from "./useEdits";
import { ApiFailure, archiveDownload, projectRequest } from "./api";

export function usePortable(edits: ReturnType<typeof useEdits>) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  async function save() {
    if (busy) return;
    setBusy(true);setMessage("");
    try {
      if (!await edits.flushBeforeAction()) { setMessage("Завершите ввод и сохраните правки перед сохранением файла проекта.");return; }
      const current = edits.acknowledged();if (!current) return;
      const captured = await projectRequest(`/v1/projects/${current.projectId}`);
      if (!await edits.flushBeforeAction() || edits.acknowledged()?.documentRevision !== captured.workspace.documentRevision) {
        setMessage("Текст изменился. Повторите сохранение файла проекта.");return;
      }
      const blob = await archiveDownload(current.projectId, { projectRevision: captured.workspace.projectRevision, documentRevision: captured.workspace.documentRevision });
      const url = URL.createObjectURL(blob), link = document.createElement("a");link.href = url;link.download = "project.foldcv";link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);setMessage("Файл проекта готов к скачиванию. Исходники, правки и предыдущие версии включены.");
    } catch (error) {
      setMessage(error instanceof ApiFailure && error.code === "ARCHIVE_ENTRY_LIMIT" ? "В проекте слишком много исходников для переносимого файла. Текущий проект остаётся сохранён локально."
        : error instanceof ApiFailure && ["ARCHIVE_JSON_LIMIT", "ARCHIVE_EXPANDED_LIMIT", "ARCHIVE_ENTRY_SIZE_LIMIT", "ARCHIVE_SIZE_LIMIT"].includes(error.code)
          ? "Проект слишком большой для переносимого файла. Текущий проект остаётся сохранён локально."
          : "Не удалось сохранить файл проекта. Текущие правки остаются в редакторе; проверьте сохранение и повторите действие.");
    }
    finally { setBusy(false); }
  }
  return { busy, message, save };
}
