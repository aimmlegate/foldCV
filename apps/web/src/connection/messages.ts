import type { ConnectionState, ProviderSummary } from "./workflow";

type Names = Pick<ProviderSummary, "display" | "subscription">;

export function connectionMessage(state: ConnectionState, { display, subscription }: Names): string {
  const messages: Record<ConnectionState, string> = {
    unchecked: "Подключение ещё не проверено.", detached: "Модель отключена от FoldCV. Вход в CLI остаётся в силе.",
    cli_missing: `${display} не найден. Установите его для подключения подписки ${subscription}.`,
    launcher_unsupported: `Установите совместимую версию ${display} для FoldCV.`,
    unsupported_version: "Эта версия CLI не поддерживается в выбранном режиме.",
    login_required: `Нужен вход с подпиской ${subscription} в выделенном профиле CLI.`,
    api_key_mode: `Обнаружен вход по API-ключу. Для этого приложения нужна подписка ${subscription}.`,
    metadata_failed: "Не удалось получить сведения об аккаунте и моделях. Повторите проверку.",
    quota_exhausted: "Лимит подписки исчерпан. Дождитесь его сброса.",
    unknown_limits: "Модели доступны в списке, но сведения о лимите не получены.",
    connected: "Вход с подпиской и список моделей доступны.", login_pending: "Завершите вход в окне, открытом CLI.",
    login_failed: "Вход не завершён. Повторите, когда будете готовы.",
    cleanup_blocked: "Не удалось подтвердить остановку процесса. Проверьте CLI и перезапустите приложение.",
  };
  return messages[state];
}
