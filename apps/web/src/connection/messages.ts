import type { ConnectionState } from "./workflow";

export const connectionMessages: Record<ConnectionState, string> = {
  unchecked: "Подключение не проверено.", detached: "Модель отключена. Вход в Codex остаётся.",
  cli_missing: "Codex не найден. Установите его.",
  launcher_unsupported: "Нужна совместимая версия Codex.",
  unsupported_version: "Эта версия Codex не поддерживается.",
  login_required: "Войдите через ChatGPT.",
  api_key_mode: "Вход выполнен по API-ключу, а нужна подписка ChatGPT.",
  metadata_failed: "Не удалось получить сведения об аккаунте и моделях. Повторите проверку.",
  quota_exhausted: "Лимит подписки исчерпан. Дождитесь сброса.",
  unknown_limits: "Модели доступны, лимит неизвестен.",
  connected: "Подключено.", login_pending: "Завершите вход в открывшемся окне.",
  login_failed: "Вход не завершён. Попробуйте снова.",
  cleanup_blocked: "Не удалось остановить процесс Codex. Перезапустите приложение.",
};
