import type { AssistantTaskCatalogV1 } from "../../src/contracts/generated/assistant_task_catalog_v1";

export function taskCatalog(): AssistantTaskCatalogV1 {
  const ready = { state: "available", reasonCode: null, reason: null, remedy: null } as const;
  return { schemaVersion: 1, protocolVersion: 1, projectId: "project_1", lineage: "a".repeat(64), editorFamily: "ordinary",
    catalogRevision: "b".repeat(64), protocolEnabled: true, tasks: [{ id: "rewrite_resume", label: "Переписать резюме",
      prompt: "Подготовь вариант текущего резюме.", editors: ["ordinary"], effect: "proposal", scopes: ["resume"],
      requiredInputs: [], requiredPermissions: ["read"], reversibility: "shared_undo", limits: { operations: 100 },
      generation: ready, preparation: ready, review: ready,
      apply: { state: "permission_disabled", reasonCode: "AGENT_TOOL_DENIED", reason: "Правки запрещены.", remedy: "Разрешите правки и нажмите «Применить»." } }] };
}
