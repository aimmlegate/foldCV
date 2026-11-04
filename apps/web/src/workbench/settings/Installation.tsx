import { errorMessage } from "../../errors/messages";
import type { CliInstallation } from "../../connection/workflow";
import { OperationStatus } from "../ui/OperationStatus";

export function Installation({ value, display }: { value: CliInstallation; display: string }) {
  // The size is known once the install has found the newest release.
  const sized = value.totalBytes > 0;
  const stages = { downloading: sized ? `Скачиваем ${display}` : "Ищем последнюю версию", verifying: "Проверяем загрузку", extracting: `Устанавливаем ${display}` };
  if (value.state === "failed") return <p className="notice error" role="alert">{errorMessage(value.error ?? "install_failed", `Не удалось установить ${display}. Проверьте свободное место и повторите установку.`)}</p>;
  if (value.state === "cancelled") return <p className="small muted" role="status">Установка отменена.</p>;
  if (value.state === "downloading" || value.state === "verifying" || value.state === "extracting") {
    const downloaded = (value.downloadedBytes / 1_000_000).toFixed(1);
    const total = Math.ceil(value.totalBytes / 1_000_000);
    return <div aria-live="polite"><OperationStatus label={stages[value.state]} timed
      detail={value.state === "downloading" && sized ? `${downloaded} из ${total} МБ` : undefined} />
      <progress className="w-full accent-[var(--accent)]" aria-label={`Загрузка ${display}`} max={sized ? value.totalBytes : undefined}
        value={sized ? value.downloadedBytes : undefined} /></div>;
  }
  return null;
}
