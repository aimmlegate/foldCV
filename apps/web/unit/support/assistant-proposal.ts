import type { AssistantProposalV1 } from "../../src/contracts/generated/assistant_proposal_v1";
import type { AssistantReviewV1 } from "../../src/contracts/generated/assistant_review_v1";

export const reviewedProposal = (value: AssistantProposalV1): AssistantReviewV1 => ({ schemaVersion: 1, protocolVersion: 1,
  proposal: value, generationFinished: true, apply: { state: "available", reason: null, reasonCode: null, remedy: null } });

export function proposal(): AssistantProposalV1 {
  return { schemaVersion: 1, protocolVersion: 1, id: "proposal_1", version: 1, projectId: "project-1",
    lineage: "a".repeat(64), editorFamily: "ordinary", originRequestId: "request_1", originRunId: "run_1", taskId: "rewrite_resume",
    state: "ready", createdAt: "2026-10-23T12:00:00Z", expiresAt: "2026-10-30T12:00:00Z", contentSha256: "b".repeat(64),
    beforeSha256: "c".repeat(64), coverage: [{ schemaVersion: 1, protocolVersion: 1, unitId: "field:one", state: "changed", read: true,
      reason: "Изменение вычислено из документа." }], changes: [{ schemaVersion: 1, protocolVersion: 1, unitId: "field:one", before: "Разрабатывал API 😀",
      after: "Создавал API 😀", effect: "wording" }], operationCount: 1, reason: "Вариант готов. Документ не изменён." };
}
