import { createContext, useContext } from "react";
import type { DerivedState, DerivedValue } from "../contracts/generated/workspace_v5";

export const DerivedContext = createContext<ReadonlyMap<string, DerivedValue>>(new Map());
export function derivedValues(state: DerivedState | null | undefined): ReadonlyMap<string, DerivedValue> {
  return new Map(state?.values.map(value => [value.fieldId, value]) ?? []);
}
export function FieldDerived({ fieldId }: { fieldId: string }) {
  const value = useContext(DerivedContext).get(fieldId);
  if (!value) return null;
  return <div contentEditable={false} className="next-derived" data-derived-field={fieldId}>
    {!value.valid && <span>Дата требует уточнения</span>}
    {value.completeExposure && value.display && <span data-duration={fieldId}>{value.display}</span>}
    {value.canonicalAliases.length > 0 && !value.completeExposure && <span>Распознано технологий: {value.canonicalAliases.length}</span>}
  </div>;
}
