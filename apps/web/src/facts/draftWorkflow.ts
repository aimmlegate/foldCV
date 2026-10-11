import type { FactSheet } from "../contracts/generated/fact_sheet";
import type { DraftResult } from "../contracts/generated/draft_result";
import type { ImportedSource } from "../import/workflow";
import { validateDraftRequest, validateDraftResult, validateFactSheet, validateFactRequest } from "../contracts/validate";
import { parseDate, type ManualInput } from "./working";

export type DraftView = { pending: boolean; stage: "idle" | "normalize" | "draft";
  completed: number; error: string | null };
const encoder = new TextEncoder();

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function completed(response: Response, signal: AbortSignal): Promise<unknown> {
  if (!response.ok || !response.headers.get("content-type")?.startsWith("application/x-ndjson") || !response.body)
    throw new Error("operation rejected");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      if (signal.aborted) throw new Error("cancelled");
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 4_500_000) throw new Error("result too large");
      chunks.push(value);
    }
  } catch (error) { await reader.cancel(); throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  const lines = new TextDecoder("utf-8", { fatal: true }).decode(bytes).trim().split("\n");
  if (lines.length !== 2) throw new Error("invalid operation events");
  const events: unknown[] = lines.map((line): unknown => JSON.parse(line) as unknown);
  const first = events[0];
  const last = events.at(-1);
  if (!record(first) || first.type !== "operation.started" || first.sequence !== 1 ||
      first.transportVersion !== 1 || typeof first.requestId !== "string" ||
      !record(last) || last.type !== "operation.completed" || last.sequence !== 2 ||
      last.transportVersion !== 1 || last.requestId !== first.requestId ||
      last.baseRevision !== first.baseRevision)
    throw new Error("operation failed");
  const tail = events.at(-1);
  if (!record(tail) || !record(tail.payload) || !record(tail.payload.usage) ||
      typeof tail.payload.usage.logicalAttempts !== "number" ||
      !Number.isInteger(tail.payload.usage.logicalAttempts) ||
      tail.payload.usage.logicalAttempts < 1 || tail.payload.usage.logicalAttempts > 2)
    throw new Error("invalid operation result");
  return tail.payload.result;
}

export function mergeDraftSheet(normalized: FactSheet, accepted: FactSheet | null): FactSheet {
  const retained = accepted?.facts.filter((fact) => fact.origin === "user" && !normalized.facts.some((newFact) => newFact.id === fact.id)) ?? [];
  const corrections = Object.fromEntries(Object.entries(accepted?.userCorrections ?? {}).filter(([sourceId, userId]) =>
    normalized.facts.some((fact) => fact.id === sourceId) &&
    [...normalized.facts, ...retained].some((fact) => fact.id === userId)));
  const facts = [...normalized.facts, ...retained].map((fact) => {
    const sources = normalized.facts.filter((item) => corrections[item.id] === fact.id);
    const jobIds = new Set(sources.map((item) => item.jobId).filter((id) => id !== null));
    const source = sources.length === 1 && jobIds.size === 1 ? sources[0] : null;
    return source?.jobId && normalized.employment?.some((job) => job.id === source.jobId) ?
      { ...fact, jobId: source.jobId, subprojectId: source.subprojectId } : fact;
  });
  const employment = normalized.employment?.map((job) => ({ ...job,
    factIds: [...job.factIds, ...facts.filter((fact) => fact.jobId === job.id && !job.factIds.includes(fact.id))
      .map((fact) => fact.id)] }));
  const sheet: FactSheet = { ...normalized, revision: (normalized.revision ?? 1) + (retained.length ? 1 : 0),
    facts, employment: employment ?? [], userCorrections: corrections };
  if (!validateFactSheet(sheet)) throw new Error("Некорректная связь исправлений.");
  return sheet;
}

export class DraftWorkflow {
  private epoch = 0;
  private abort: AbortController | null = null;
  view: DraftView = { pending: false, stage: "idle", completed: 0, error: null };

  constructor(private readonly onChange: (view: DraftView) => void,
              private readonly onComplete: (sheet: FactSheet, draft: DraftResult, manual: ManualInput) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  private publish(view: DraftView): void { this.view = view; this.onChange(view); }

  cancel(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    this.publish({ ...this.view, pending: false, stage: "idle", error: null });
  }

  async run(entries: ImportedSource[], accepted: FactSheet | null, manual: ManualInput,
            isCurrent: () => boolean): Promise<void> {
    this.cancel();
    const epoch = this.epoch;
    const abort = new AbortController();
    this.abort = abort;
    try {
      const asOf = parseDate(manual.asOf);
      if (!asOf) throw new Error("Укажите дату наблюдения перед составлением черновика.");
      const factRequest = { transportVersion: 1, baseRevision: 1,
        sources: entries.map((entry) => ({ result: entry.result, overlays: entry.overlays })) };
      if (!validateFactRequest(factRequest) || encoder.encode(JSON.stringify(factRequest)).length > 1_048_576)
        throw new Error("Источники превышают предел составления черновика.");
      this.publish({ ...this.view, pending: true, stage: "normalize", error: null });
      const normalResponse = await this.request("/v1/facts/normalize", { method: "POST", credentials: "same-origin",
        cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(factRequest), signal: abort.signal });
      const normalized: unknown = await completed(normalResponse, abort.signal);
      if (epoch !== this.epoch) return;
      if (!isCurrent()) { this.cancel(); return; }
      if (!validateFactSheet(normalized)) throw new Error("Некорректный лист фактов.");
      const sheet = mergeDraftSheet(normalized, accepted);
      const draftRequest = { transportVersion: 1, sheet, sourceFingerprint: sheet.sourceFingerprint,
        baseRevision: sheet.revision ?? 1, asOf, sourceLanguage: manual.language,
        preserveManualProfile: manual.metrics.some((metric) => metric.jobId === null) };
      if (!validateDraftRequest(draftRequest) || encoder.encode(JSON.stringify(draftRequest)).length > 1_048_576)
        throw new Error("Лист фактов превышает предел составления черновика.");
      this.publish({ ...this.view, pending: true, stage: "draft", completed: this.view.completed + 1, error: null });
      const draftResponse = await this.request("/v1/facts/draft", { method: "POST", credentials: "same-origin",
        cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draftRequest), signal: abort.signal });
      const drafted: unknown = await completed(draftResponse, abort.signal);
      if (epoch !== this.epoch) return;
      if (!isCurrent()) { this.cancel(); return; }
      if (!validateDraftResult(drafted) || drafted.sourceFingerprint !== sheet.sourceFingerprint ||
          drafted.baseRevision !== sheet.revision) throw new Error("Черновик относится к старому листу фактов.");
      this.onComplete(sheet, drafted, structuredClone(manual));
      this.publish({ ...this.view, pending: false, stage: "idle", completed: this.view.completed + 1, error: null });
    } catch {
      if (epoch === this.epoch) this.publish({ ...this.view, pending: false, stage: "idle",
        error: "Не удалось составить черновик. Исходники и принятые правки сохранены." });
    } finally { if (this.abort === abort) this.abort = null; }
  }
}
