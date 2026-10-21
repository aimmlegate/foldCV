import { errorMessage } from "../../errors/messages";
import type { CliInstallation } from "../../connection/workflow";
import { OperationStatus } from "../ui/OperationStatus";

const stages = { downloading: "Скачиваем Codex", verifying: "Проверяем загрузку", extracting: "Устанавливаем Codex" };

export function Installation({ value }: { value: CliInstallation }) {
  if (value.state === "failed") return <p className="notice error" role="alert">{errorMessage(value.error ?? "install_failed", "Не удалось установить Codex. Проверьте свободное место и повторите установку.")}</p>;
  if (value.state === "cancelled") return <p className="small muted" role="status">Установка отменена. Можно попробовать снова.</p>;
  if (value.state === "downloading" || value.state === "verifying" || value.state === "extracting") {
    const downloaded = (value.downloadedBytes / 1_000_000).toFixed(1);
    const total = Math.ceil(value.totalBytes / 1_000_000);
    return <div aria-live="polite"><OperationStatus label={stages[value.state]} timed
      detail={value.state === "downloading" ? `${downloaded} из ${total} МБ` : "Подготавливаем проверенную версию для FoldCV."} />
      <progress className="w-full accent-[var(--accent)]" aria-label="Загрузка Codex" max={value.totalBytes} value={value.downloadedBytes} /></div>;
  }
  return null;
}
