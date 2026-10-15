export function commandBlock<T extends { id: string; type: string }>(id: string, read: (id: string) => T | undefined): T {
  const block = read(id);
  if (!block || block.type === "region") throw new Error("Блок недоступен. Откройте меню другого блока.");
  return block;
}
