import type { AssistantTaskCatalogV1 } from "../contracts/generated/assistant_task_catalog_v1";

export function Capabilities({ catalog, busy, choose }: { catalog: AssistantTaskCatalogV1; busy: boolean; choose: (text: string) => void }) {
  if (!catalog.protocolEnabled) return null;
  return <details className="border-b border-outline px-4 py-2 text-content">
    <summary className="cursor-pointer">Что умеет помощник</summary>
    <p className="my-2">Изменения сначала показываются для просмотра. Применение требует отдельного нажатия «Применить».</p>
    <ul className="max-h-64 space-y-3 overflow-y-auto" aria-label="Возможности помощника">
      {catalog.tasks.map(task => <li key={task.id}>
        {task.prompt && task.generation.state === "available"
          ? <button className="text-button" type="button" disabled={busy} onClick={() => { if (task.prompt) choose(task.prompt); }}>{task.label}</button>
          : <span>{task.label}</span>}
        {task.generation.reason && <p>{task.generation.reason} {task.generation.remedy}</p>}
        {task.effect !== "read" && task.apply.reason && task.apply.reasonCode !== task.generation.reasonCode
          && <p>{task.effect === "export" ? "Экспорт" : "Применение"}: {task.apply.reason} {task.apply.remedy}</p>}
        {task.generation.state !== "available" && task.review.state === "available" && <p>Локальный просмотр подготовленного результата доступен.</p>}
      </li>)}
    </ul>
  </details>;
}
