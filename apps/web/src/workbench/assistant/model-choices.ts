export type ModelChoice = { model: string; state: string };

/** The saved model is "unavailable" only when the service refused it and its loaded catalog lists other models. */
export function modelChoices(selected: string, models: readonly ModelChoice[], refused: boolean): ModelChoice[] {
  if (!selected || models.some(item => item.model === selected)) return [...models];
  if (!refused || models.length === 0) return [{ model: selected, state: "unverified" }, ...models];
  return [{ model: selected, state: "unavailable" }, ...models];
}
