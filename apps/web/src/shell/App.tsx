import * as Tabs from "@radix-ui/react-tabs";
import { useEffect, useState } from "react";

type ThemeMode = "light" | "dark" | "system";
const THEME_KEY = "foldcv-theme";

function savedMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

function isThemeMode(value: string): value is ThemeMode {
  return value === "light" || value === "dark" || value === "system";
}

function resolveTheme(mode: ThemeMode, darkSystem: boolean): "light" | "dark" {
  return mode === "system" ? (darkSystem ? "dark" : "light") : mode;
}

export function App() {
  const [mode, setMode] = useState<ThemeMode>(savedMode);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = resolveTheme(mode, media.matches);
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);

  function changeTheme(next: ThemeMode) {
    if (next === "system") {
      localStorage.removeItem(THEME_KEY);
    } else {
      localStorage.setItem(THEME_KEY, next);
    }
    setMode(next);
  }

  return <main className="min-h-screen bg-surface text-content">
    <header className="border-b border-outline px-5 py-4">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
        <h1 className="text-xl font-bold">FoldCV</h1>
        <label className="flex items-center gap-2 text-sm">
          <span>Тема</span>
          <select aria-label="Тема" className="rounded border border-outline bg-surface p-2" value={mode}
            onChange={(event) => {
              if (isThemeMode(event.target.value)) changeTheme(event.target.value);
            }}>
            <option value="system">Системная</option>
            <option value="light">Светлая</option>
            <option value="dark">Тёмная</option>
          </select>
        </label>
      </div>
    </header>
    <div className="mx-auto max-w-5xl p-5">
      <Tabs.Root defaultValue="import">
        <Tabs.List aria-label="Разделы" className="mb-5 flex gap-2 border-b border-outline">
          <Tabs.Trigger value="import" className="border-b-2 border-content px-3 py-2">Импорт</Tabs.Trigger>
          <Tabs.Trigger value="editor" disabled className="px-3 py-2 opacity-50">Редактор</Tabs.Trigger>
          <Tabs.Trigger value="export" disabled className="px-3 py-2 opacity-50">Экспорт</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="import" className="grid gap-5 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <section className="rounded border border-outline bg-panel p-5">
            <h2 className="mb-3 text-lg font-semibold">Исходное резюме</h2>
            <label htmlFor="source-text" className="mb-2 block">Вставьте текст резюме</label>
            <textarea id="source-text" className="min-h-48 w-full rounded border border-outline bg-surface p-3" />
            <p className="mt-3 text-sm text-muted">Локальный импорт будет доступен после подключения сервиса.</p>
          </section>
          <aside className="rounded border border-outline bg-panel p-5">
            <h2 className="mb-3 text-lg font-semibold">Подключение</h2>
            <p role="status">Генерация недоступна: профиль CLI не прошёл проверку безопасности.</p>
            <button disabled className="mt-4 rounded bg-muted px-3 py-2 text-surface">Обработать текст</button>
          </aside>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  </main>;
}
