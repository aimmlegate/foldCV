import type { WriterMode } from "../../background/writer";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";

export function editorNoticeState(mode: WriterMode | null, warning: string, syncRecords: RichProjectResponse["workspace"]["syncRecords"]) {
  const recovery = mode === "recovering" || mode === "read_only";
  // Older dismissals used stale with no error code.
  const records = syncRecords.filter(record => !(record.kind === "rewrite" && record.status === "pending" && record.ready && record.rewriteResult != null)
    && (["failed", "conflict", "pending"].includes(record.status) ||
      record.status === "stale" && record.errorCode !== null && record.errorCode !== "USER_DISMISSED"));
  return { recovery, records, count: Number(recovery) + (warning ? 1 : 0) + records.length };
}
