export function updateNotificationCounts(previous: ReadonlyMap<string, number>, id: string, count: number): ReadonlyMap<string, number> {
  if ((previous.get(id) ?? 0) === count) return previous;
  const next = new Map(previous);
  if (count) next.set(id, count); else next.delete(id);
  return next;
}

export function notificationTotal(counts: ReadonlyMap<string, number>): number {
  return [...counts.values()].reduce((total, count) => total + count, 0);
}
