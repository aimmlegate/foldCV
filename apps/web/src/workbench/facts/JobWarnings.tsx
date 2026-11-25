import { Icon } from "../ui/Icon";

/** «Пересекается с …» for the other jobs' names: the first two, then «и ещё N» (D182, J5-c). */
export function overlapLine(names: readonly string[]): string {
  const shown = names.slice(0, 2).map(name => `«${name}»`).join(", ");
  return `Пересекается с ${shown}${names.length > 2 ? ` и ещё ${names.length - 2}` : ""}`;
}

/** Subdued warning lines of a job's dates (D182, J7): information only, never a refusal. Nothing when there are none. */
export function JobWarnings({ lines, live = false }: { lines: readonly string[]; live?: boolean }) {
  // The dialog's region stays in place while it is empty, so a screen reader hears the lines that come later.
  if (!lines.length && !live) return null;
  return <div className="fact-warnings" {...(live ? { role: "status" } : {})}>
    {lines.map(line => <p className="fact-warning" key={line}><Icon name="warning" />{line}</p>)}
  </div>;
}
