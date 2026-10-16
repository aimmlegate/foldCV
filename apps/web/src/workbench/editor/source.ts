export function sourceText(source: { parser: string; units: readonly { order: number; text: string }[] }): string {
  return [...source.units].sort((a, b) => a.order - b.order).map(unit => unit.text).join(source.parser === "utf8" ? "" : "\n\n");
}
