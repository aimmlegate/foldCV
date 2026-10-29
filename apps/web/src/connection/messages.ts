import type { ConnectionState, ProviderSummary } from "./workflow";

type Names = Pick<ProviderSummary, "display" | "subscription">;

export function connectionMessage(state: ConnectionState, { display, subscription }: Names): string {
  const messages: Record<ConnectionState, string> = {
    unchecked: "Подключение не проверено.", detached: `Модель отключена. Вход в ${display} остаётся.`,
    cli_missing: `${display} не найден. Установите его.`,
    launcher_unsupported: `Нужна совместимая версия ${display}.`,
    unsupported_version: `Эта версия ${display} не поддерживается.`,
    login_required: `Войдите через ${subscription}.`,
    api_key_mode: `Вход выполнен по API-ключу, а нужна подписка ${subscription}.`,
    metadata_failed: "Не удалось получить сведения об аккаунте и моделях. Повторите проверку.",
    quota_exhausted: "Лимит подписки исчерпан. Дождитесь сброса.",
    unknown_limits: "Модели доступны, лимит неизвестен.",
    connected: "Подключено.", login_pending: "Завершите вход в открывшемся окне.",
    login_failed: "Вход не завершён. Попробуйте снова.",
    cleanup_blocked: `Не удалось остановить процесс ${display}. Перезапустите приложение.`,
  };
  return messages[state];
}
