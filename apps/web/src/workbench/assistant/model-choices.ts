export type ModelChoice = { model: string; state: string; provider?: string | null };
export type ModelChoiceGroup = { label: string | null; choices: ModelChoice[] };

/** The saved model is not "unavailable" until a ready catalog lists other models and omits it. */
export function modelChoices(selected: string, models: readonly ModelChoice[], ready: boolean): ModelChoice[] {
  if (!selected || models.some(item => item.model === selected)) return [...models];
  if (!ready || models.length === 0) return [{ model: selected, state: "unverified" }, ...models];
  return [{ model: selected, state: "unavailable" }, ...models];
}

/** Choices grouped by provider in the server's order (D119). One provider shows a plain list; a saved model no provider
 * lists stays first, outside the groups. */
export function choiceGroups(choices: readonly ModelChoice[]): ModelChoiceGroup[] {
  const labels = [...new Set(choices.flatMap(item => item.provider ?? []))];
  if (labels.length < 2) return [{ label: null, choices: [...choices] }];
  const loose = choices.filter(item => !item.provider);
  return [...(loose.length ? [{ label: null, choices: loose }] : []),
    ...labels.map(label => ({ label, choices: choices.filter(item => item.provider === label) }))];
}
