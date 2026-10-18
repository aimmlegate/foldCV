import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";

export type ImportGeneration = NonNullable<RichProjectResponse["generation"]>;
type FoundJob = { id: string; employer: string; role: string };
export type ImportProgress = { name: string; title: string; facts: number; jobs: FoundJob[]; technologies: string[];
  sections: number; saved: boolean; pages: number; excerpt: string; stamp: string };

export const importStages = [
  { stage: "assess_resume", label: "Читаем исходник" },
  { stage: "normalize_semantics", label: "Извлекаем факты" },
  { stage: "assemble", label: "Применяем макет" },
  { stage: "render", label: "Готовим DOCX" },
] as const;

export function importProgress(response: RichProjectResponse): ImportProgress {
  const { workspace, generation } = response;
  const current = workspace.preDraft?.importDraft;
  const draft = current?.runId === generation?.id ? current : null;
  const project = workspace.project;
  const source = workspace.preDraft?.sources.find(item => item.id === workspace.preDraft?.selectedSourceId);
  const result: ImportProgress = { name: draft?.profile?.name ?? "", title: draft?.profile?.title ?? "", facts: 0,
    jobs: [], technologies: [], sections: 0, saved: false,
    pages: new Set(source?.units.filter(unit => unit.location.kind === "page").map(unit => unit.location.index)).size,
    excerpt: source?.units.filter(unit => unit.text.trim()).slice(0, 3).map(unit => unit.text.trim()).join("\n").slice(0, 360) ?? "",
    stamp: `${generation?.id ?? ""}:${generation?.stage ?? ""}:${draft?.sequence ?? 0}:${project ? workspace.projectRevision : 0}` };
  const technology = (display: string, technical?: boolean | null) => {
    const name = display.trim();
    if (name && technical !== false && !result.technologies.some(item => item.toLocaleLowerCase() === name.toLocaleLowerCase()))
      result.technologies.push(name);
  };
  if (draft) {
    result.facts = draft.facts?.length ?? 0;
    result.sections = draft.blocks?.filter(block => block.kind === "section").length ?? 0;
    result.saved = (draft.sequence ?? 0) > 0;
    for (const fact of draft.facts ?? []) {
      const record = fact.record;
      if (record?.kind === "employment") {
        result.jobs.push({ id: fact.id, employer: record.employer ?? "", role: record.role ?? "" });
        record.technologies?.forEach(item => typeof item === "string" ? technology(item) : technology(item.display, item.technical));
      } else if (record?.kind === "technology") technology(record.display, record.technical);
    }
  } else if (project) {
    result.saved = true;
    result.facts = project.facts.records.length;
    result.sections = project.document.regions.reduce((count, region) => count + region.blocks.filter(block => block.type === "section").length, 0);
    for (const record of project.facts.records) {
      if (record.kind === "candidate") { result.name = record.name.rawText; result.title = record.title.rawText; }
      else if (record.kind === "employment") result.jobs.push({ id: record.id, employer: record.employer.rawText, role: record.role.rawText });
      else if (record.kind === "technology") technology(record.display.rawText, record.technical);
    }
  }
  return result;
}

export function elapsedLabel(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(Number.isFinite(milliseconds) ? milliseconds / 1000 : 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function progressMessage(generation: ImportGeneration, saved: boolean, quietSeconds: number): string {
  if (generation.status === "queued") return "Задача в очереди. Начнём, как только модель освободится.";
  if (generation.stage === "render") return "Собираем редактируемый файл с оформлением и изображениями.";
  if (generation.stage === "assemble") return "Размещаем содержание по разделам и применяем оформление.";
  if (quietSeconds >= 20) return saved ? "Новых сохранений пока нет. Ждём следующую часть результата."
    : "Первых результатов пока нет. Ожидаем ответ модели.";
  return saved ? "Промежуточный результат сохранён. Разбор продолжается." : "Результаты появятся здесь по мере сохранения.";
}
