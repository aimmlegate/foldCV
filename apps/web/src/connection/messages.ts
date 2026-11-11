import type { ConnectionState, Leaving, ProviderEntry } from "./workflow";

type Names = Pick<ProviderEntry, "display" | "subscription">;

/** What Settings asks once more before a sign-out or a clearing. Each touches only the app's own profile. */
export function leaveQuestion(leaving: Leaving, { display }: Names, account?: string | null): { title: string; body: string; confirm: string } {
  if (leaving === "logout") return { title: `Выйти из аккаунта ${display}?`, confirm: "Выйти",
    body: `Приложение выйдет из аккаунта${account ? ` ${account}` : ""}. Идущий импорт, правка или ответ помощника прервутся. ` +
      `Вход в ${display} в терминале и других программах останется.` };
  return { title: `Очистить данные ${display}?`, confirm: "Очистить",
    body: `Удалятся настройки, журналы и временные файлы ${display} в профиле приложения. Резюме и шаблоны не изменятся, войти можно будет снова.` };
}

export function connectionMessage(state: ConnectionState, { display, subscription }: Names): string {
  const messages: Record<ConnectionState, string> = {
    unchecked: "Подключение не проверено.", detached: `Модель отключена. Вход в ${display} остаётся.`,
    cli_missing: `${display} не найден. Установите его.`,
    launcher_unsupported: `Нужна совместимая версия ${display}.`,
    unsupported_version: `Установленный ${display} не подходит.`,
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
