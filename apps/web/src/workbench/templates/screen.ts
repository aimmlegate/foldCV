/** The main area shows the resume, Settings or the templates screen. */
export type Screen = "resume" | "settings" | "templates";

const titles: Record<Exclude<Screen, "resume">, string> = { settings: "Настройки", templates: "Шаблоны" };

/** The header title: the resume's own title on its screen, else the screen's name. */
export function screenTitle(screen: Screen, resume: string): string {
  return screen === "resume" ? resume : titles[screen];
}

/** Settings and templates stay mounted after their first visit, so switching screens keeps their unsaved text. */
export function visit(visited: ReadonlySet<Screen>, screen: Screen): ReadonlySet<Screen> {
  return visited.has(screen) ? visited : new Set([...visited, screen]);
}
