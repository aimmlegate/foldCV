import { errorMessage } from "../../errors/messages";
import type { CliInstallation } from "../../connection/workflow";
import { OperationStatus } from "../ui/OperationStatus";

export function Installation({ value, display }: { value: CliInstallation; display: string }) {
  const stages = { downloading: `Скачиваем ${display}`, verifying: "Проверяем загрузку", extracting: `Устанавливаем ${display}` };
  if (value.state === "failed") return <p className="notice error" role="alert">{errorMessage(value.error ?? "install_failed", `Не удалось установить ${display}. Проверьте свободное место и повторите установку.`)}</p>;
  if (value.state === "cancelled") return <p className="small muted" role="status">Установка отменена.</p>;
  if (value.state === "downloading" || value.state === "verifying" || value.state === "extracting") {
    const downloaded = (value.downloadedBytes / 1_000_000).toFixed(1);
    const total = Math.ceil(value.totalBytes / 1_000_000);
    return <div aria-live="polite"><OperationStatus label={stages[value.state]} timed
      detail={value.state === "downloading" ? `${downloaded} из ${total} МБ` : undefined} />
      <progress className="w-full accent-[var(--accent)]" aria-label={`Загрузка ${display}`} max={value.totalBytes} value={value.downloadedBytes} /></div>;
  }
  return null;
}
