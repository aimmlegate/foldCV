/** One active import remark per block. A remark with no block, or a second remark on the same block, is not shown. */

export type NoticeInput = { id: string; state: string; message: string; blockIds: readonly string[] };
export type BlockNotice = { id: string; blockId: string; message: string };

export function blockNotices(issues: readonly NoticeInput[]): BlockNotice[] {
  const seen = new Set<string>();
  const notes: BlockNotice[] = [];
  for (const issue of issues) {
    if (issue.state !== "active") continue;
    const message = issue.message.trim();
    if (!message) continue;
    const blockId = issue.blockIds.find(id => id.length > 0 && !seen.has(id));
    if (!blockId) continue;
    seen.add(blockId);
    notes.push({ id: issue.id, blockId, message });
  }
  return notes;
}
