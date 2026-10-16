import type { JobFixedRequestV1 } from "../contracts/generated/background_fixed_request_v1";
import type { JobFixedReplyV1 } from "../contracts/generated/background_fixed_reply_v1";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { RichApiFailure } from "../rich/api";
import { JobsApi } from "./api";

export type FixedCommand = JobFixedRequestV1["command"];
type FixedTransport = Pick<JobsApi, "projectJobs" | "fixed">;

export function fixedAction(command: FixedCommand): string | null {
  if (command.kind === "processing") return null;
  if ("capture" in command) return command.capture.actionId;
  if (command.kind === "rewrite") return command.request.selection.capture.actionId;
  return command.request.capture.actionId;
}

export function operationSync(response: RichProjectResponse, project: string, action: string) {
  if (response.workspace.projectId !== project) throw new RichApiFailure("INVALID_RESULT");
  const records = response.workspace.syncRecords.filter(record => record.actionId === action);
  if (records.length !== 1 || !records[0]) throw new RichApiFailure("INVALID_RESULT");
  return records[0];
}

export class FixedOperations {
  private readonly requests = new Map<string, { body: string; request: Promise<JobFixedRequestV1> }>();
  constructor(readonly project: string, private readonly api: FixedTransport = new JobsApi(project)) {}

  async submit(command: FixedCommand, current: () => boolean = () => true): Promise<JobFixedReplyV1> {
    const action = fixedAction(command), key = action === null ? crypto.randomUUID() : `${command.kind}:${action}`;
    let retained = this.requests.get(key);
    const body = JSON.stringify(command);
    if (retained && retained.body !== body) throw new RichApiFailure("JOB_IDEMPOTENCY_CONFLICT");
    if (!retained) {
      const request = this.api.projectJobs().then(project => {
        if (project.projectId !== this.project) throw new RichApiFailure("INVALID_RESULT");
        return { schemaVersion: 1 as const, lineage: project.lineage,
          requestEpoch: project.requestEpoch, clientRequestId: crypto.randomUUID(), command };
      });
      retained = { body, request };
      this.requests.set(key, retained);
    }
    let request: JobFixedRequestV1;
    try { request = await retained.request; }
    catch (error) { if (this.requests.get(key) === retained) this.requests.delete(key); throw error; }
    if (!current()) throw new RichApiFailure("STALE_SELECTION");
    const reply = await this.api.fixed(request), job = reply.job;
    const processing = command.kind === "processing";
    if (reply.projectId !== this.project || job.submission.identity.projectId !== this.project
      || job.submission.identity.lineage !== request.lineage
      || job.submission.identity.requestId !== request.clientRequestId
      || job.submission.identity.requestEpoch !== request.requestEpoch
      || reply.actionId !== action || (reply.syncId === null) !== processing
      || !processing && reply.syncId !== job.submission.input.id
      || processing !== (job.submission.kind === "processing")
      || command.kind === "rewrite" && job.submission.kind !== "rewrite") throw new RichApiFailure("INVALID_RESULT");
    return reply;
  }
}
