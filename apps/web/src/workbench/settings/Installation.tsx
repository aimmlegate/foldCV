import type { CliInstallation } from "../../connection/workflow";
import { OperationStatus } from "../ui/OperationStatus";

const errors: Record<string, string> = {
  download_failed: "Не удалось скачать Codex. Проверьте интернет и повторите установку.",
  checksum_failed: "Загруженный файл не прошёл проверку. Повторите установку.",
  invalid_package: "Пакет Codex не прошёл проверку. Повторите установку.",
  unsafe_directory: "Папка установки недоступна. Проверьте права доступа.",
  busy: "Codex уже устанавливается в другом окне. Дождитесь завершения и проверьте подключение.",
  unsupported_platform: "Автоматическая установка пока доступна только на Mac с Apple Silicon.",
  install_failed: "Не удалось установить Codex. Проверьте свободное место и повторите установку.",
};
const stages = { downloading: "Скачиваем Codex", verifying: "Проверяем загрузку", extracting: "Устанавливаем Codex" };

export function Installation({ value }: { value: CliInstallation }) {
  if (value.state === "failed") return <p className="notice error" role="alert">{errors[value.error ?? ""] ?? errors.install_failed}</p>;
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
