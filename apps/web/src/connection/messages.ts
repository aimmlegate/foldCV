import type { ConnectionState } from "./workflow";

export const connectionMessages: Record<ConnectionState, string> = {
  unchecked: "Подключение ещё не проверено.", detached: "Модель отключена от FoldCV. Вход в CLI остаётся в силе.",
  cli_missing: "Codex не найден. Установите его для подключения ChatGPT.",
  launcher_unsupported: "Установите совместимую версию Codex для FoldCV.",
  unsupported_version: "Эта версия CLI не поддерживается в выбранном режиме.",
  login_required: "Нужен вход с подпиской ChatGPT в выделенном профиле CLI.",
  api_key_mode: "Обнаружен вход по API-ключу. Для этого приложения нужна подписка ChatGPT.",
  metadata_failed: "Не удалось получить сведения об аккаунте и моделях. Повторите проверку.",
  quota_exhausted: "Лимит подписки исчерпан. Дождитесь его сброса.",
  unknown_limits: "Модели доступны в списке, но сведения о лимите не получены.",
  connected: "Вход с подпиской и список моделей доступны.", login_pending: "Завершите вход в окне, открытом CLI.",
  login_failed: "Вход не завершён. Повторите, когда будете готовы.",
  cleanup_blocked: "Не удалось подтвердить остановку процесса. Проверьте CLI и перезапустите приложение.",
};
