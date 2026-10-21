import { errorMessage } from "../errors/messages";
import type { AgentFinding } from "../contracts/generated/agent_finding";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { documentCells } from "../rich/document-cells";
import { factCells } from "../rich/fact-cells";
import type { CellValue } from "../rich/history";
import type { AssistantView } from "./controller";

export function errorText(code: string | null): string {
  return code ? errorMessage(code, "Не удалось завершить задачу. Сохранённые результаты доступны в диалоге.") : "";
}
export function runText(view: AssistantView): string {
  if (view.submitting) return "Отправляем задачу…";
  if (view.pendingSend) return "Ответ на отправку потерян. Повторите ту же отправку или остановите задачу.";
  const labels = { queued: "Ожидает очереди", running: "Выполняется", waiting_for_editor: "Сохраняем изменения",
    cancelling: "Останавливаем…", cancelled: "Остановлено", interrupted: "Прервано", failed: "Не удалось завершить", completed: "Завершено" };
  return view.run ? labels[view.run.state] : "";
}
export function canSend(view: AssistantView, applying = false): boolean {
  return !view.submitting && !view.loading && !applying && (!view.run || ["completed", "failed", "cancelled", "interrupted"].includes(view.run.state))
    && (view.pendingSend || view.capabilities?.ready === true) && !!view.draft.trim() && [...view.draft].length <= 8000;
}
export function submitKey(key: string, shift: boolean, composing: boolean, nativeComposing: boolean, keyCode: number): boolean {
  return key === "Enter" && !shift && !composing && !nativeComposing && keyCode !== 229;
}
export function sourceUrl(value: string): string | null {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
export type DrawerSize = { collapsed: boolean; height: number };
export function drawerSize(value: unknown): DrawerSize {
  if (typeof value !== "object" || value === null) return { collapsed: true, height: 320 };
  return { collapsed: "collapsed" in value && typeof value.collapsed === "boolean" ? value.collapsed : true,
    height: "height" in value && typeof value.height === "number" && Number.isFinite(value.height) ? Math.max(200, Math.min(520, value.height)) : 320 };
}
export function anchorCurrent(anchor: AgentFinding["anchors"][number], response: RichProjectResponse, current: ReadonlyMap<string, CellValue>): boolean {
  const project = response.workspace.project;
  if (!project || !anchor.dependencies.length) return false;
  const blocks = new Map<string, number>();
  const visit = (items: typeof project.document.regions[number]["blocks"]) => { for (const block of items) { blocks.set(block.id, block.revision); visit(block.children); } };
  project.document.regions.forEach(region => visit(region.blocks));
  if (!anchor.dependencies.every(dep => dep.kind === "block" ? blocks.get(dep.id) === dep.revision
    : dep.kind === "record" && project.facts.records.find(record => record.id === dep.id)?.revision === dep.revision)) return false;
  const baseline = new Map([...documentCells(project.document, new Map()), ...factCells(project.facts)]);
  const keys = anchor.blockId ? [`block:${anchor.blockId}`] : [...baseline.keys()].filter(key => key === `fact:${anchor.recordId}` || key.startsWith(`fact-field:["${anchor.recordId ?? ""}",`));
  return keys.length > 0 && keys.every(key => baseline.has(key) && current.get(key) === baseline.get(key));
}
