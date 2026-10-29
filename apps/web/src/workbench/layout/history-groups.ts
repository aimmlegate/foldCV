import type { ProjectListEntry } from "../../projects/api";

export type HistoryGroups = { current: ProjectListEntry[]; archived: ProjectListEntry[] };

/** The sidebar lists: resumes in use and the archive, each in the listing order (newest added first). */
export function historyGroups(entries: readonly ProjectListEntry[]): HistoryGroups {
  const groups: HistoryGroups = { current: [], archived: [] };
  for (const entry of entries) (entry.archived ? groups.archived : groups.current).push(entry);
  return groups;
}
