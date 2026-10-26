export type ModelChoice = { model: string; state: string };

/** The saved model is not "unavailable" until a ready catalog lists other models and omits it. */
export function modelChoices(selected: string, models: readonly ModelChoice[], ready: boolean): ModelChoice[] {
  if (!selected || models.some(item => item.model === selected)) return [...models];
  if (!ready || models.length === 0) return [{ model: selected, state: "unverified" }, ...models];
  return [{ model: selected, state: "unavailable" }, ...models];
}
