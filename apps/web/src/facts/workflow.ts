import type { FactSheet, TextFact } from "../contracts/generated/fact_sheet";
import { validateFactSheet } from "../contracts/validate";
import type { ImportedSource } from "../import/workflow";

export type FactView = { sheet: FactSheet | null; pending: boolean; stale: boolean; error: string | null };
const encoder = new TextEncoder();

function manualSheet(entries: ImportedSource[], assertions: TextFact[]): FactSheet {
  return { transportVersion: 1, sourceFingerprint: "manual", revision: 1, facts: assertions, employment: [],
    proposedFactIds: [], overlayFactRefs: {}, userCorrections: {}, candidates: [], units: entries.flatMap((entry) => [
      ...entry.result.units.map((unit) => ({ sourceId: entry.result.sourceId, unitId: unit.id,
        disposition: "unresolved" as const, factIds: [], duplicateOf: null })),
      ...entry.result.gaps.flatMap((_, index) => entry.overlays[`gap:${index}`]?.trim() ? [{
        sourceId: entry.result.sourceId, unitId: `gap:${index}`, disposition: "unresolved" as const,
        factIds: [], duplicateOf: null }] : []),
    ]), issues: [] };
}

export class FactWorkflow {
  private epoch = 0;
  private abort: AbortController | null = null;
  private entries: ImportedSource[] | null = null;
  private assertions: TextFact[] = [];
  private corrections: Record<string, string> = {};
  view: FactView = { sheet: null, pending: false, stale: false, error: null };

  constructor(private readonly onChange: (view: FactView) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  snapshot(): { view: FactView; assertions: TextFact[]; corrections: Record<string, string> } {
    return { view: { ...structuredClone(this.view), pending: false },
      assertions: structuredClone(this.assertions), corrections: { ...this.corrections } };
  }

  restore(snapshot: { view: FactView; assertions: TextFact[]; corrections: Record<string, string> },
          entries: ImportedSource[]): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    this.entries = entries;
    this.assertions = structuredClone(snapshot.assertions);
    this.corrections = { ...snapshot.corrections };
    this.publish({ ...structuredClone(snapshot.view), pending: false, error: null });
  }

  sheetForManual(entries: ImportedSource[]): FactSheet {
    const current = this.view.sheet;
    if (current && current.units.every((unit) => entries.some((entry) => entry.result.sourceId === unit.sourceId &&
      (entry.result.units.some((sourceUnit) => sourceUnit.id === unit.unitId) ||
       /^gap:(0|[1-9]\d*)$/.test(unit.unitId) && Boolean(entry.overlays[unit.unitId]?.trim()))))) return current;
    return manualSheet(entries, this.assertions);
  }

  private publish(view: FactView): void { this.view = view; this.onChange(view); }

  clear(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    this.entries = null;
    this.assertions = [];
    this.corrections = {};
    this.publish({ sheet: null, pending: false, stale: false, error: null });
  }

  cancel(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    this.publish({ ...this.view, pending: false, error: null });
  }

  addAssertion(text: string): void {
    const value = text.trim();
    if (!value || encoder.encode(value).length > 4096) {
      this.publish({ ...this.view, error: "Укажите факт до 4 КБ." });
      return;
    }
    const fact: TextFact = { id: `fact_user_${crypto.randomUUID()}`, revision: 1, kind: "text", value: { text: value },
      evidence: [], origin: "user", importance: "normal", jobId: null, subprojectId: null };
    this.assertions = [...this.assertions, fact];
    const sheet = this.view.sheet ?? manualSheet(this.entries ?? [], []);
    this.publish({ ...this.view, sheet: { ...sheet, revision: (sheet.revision ?? 1) + 1,
      facts: [...sheet.facts, fact] }, error: null });
  }

  editAssertion(id: string, text: string): void {
    const value = text.trim();
    if (!value || encoder.encode(value).length > 4096) {
      this.publish({ ...this.view, error: "Укажите факт до 4 КБ." });
      return;
    }
    const previous = this.assertions.find((fact) => fact.id === id);
    if (!previous || !this.view.sheet) return;
    const changed: TextFact = { ...previous, revision: previous.revision + 1, value: { text: value } };
    this.assertions = this.assertions.map((fact) => fact.id === id ? changed : fact);
    this.publish({ ...this.view, sheet: { ...this.view.sheet, revision: (this.view.sheet.revision ?? 1) + 1,
      facts: this.view.sheet.facts.map((fact) => fact.id === id ? changed : fact) }, error: null });
  }

  correctFact(sourceFactId: string, text: string): void {
    const sourceFact = this.view.sheet?.facts.find((fact) => fact.id === sourceFactId && fact.origin === "source");
    if (!sourceFact) return;
    const previousId = this.corrections[sourceFactId];
    if (previousId) { this.editAssertion(previousId, text); return; }
    const before = this.assertions.length;
    this.addAssertion(text);
    if (this.assertions.length === before) return;
    const replacement = this.assertions.at(-1);
    if (!replacement || !this.view.sheet) return;
    this.corrections = { ...this.corrections, [sourceFactId]: replacement.id };
    this.publish({ ...this.view, sheet: { ...this.view.sheet, userCorrections: this.corrections }, error: null });
  }

  sourcesChanged(entries: ImportedSource[]): void {
    if (entries === this.entries) return;
    this.entries = entries;
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    if (!entries.length) { this.clear(); return; }
    this.publish({ ...this.view, pending: false, stale: true, error: null });
  }

  async update(entries: ImportedSource[]): Promise<void> {
    this.sourcesChanged(entries);
    if (!entries.length) return;
    this.epoch += 1;
    const epoch = this.epoch;
    this.abort?.abort();
    this.abort = null;
    const body = JSON.stringify({ transportVersion: 1, sources: entries.map((entry) => ({ result: entry.result, overlays: entry.overlays })) });
    if (encoder.encode(body).length > 1_048_576) {
      this.publish({ ...this.view, sheet: this.view.sheet ?? manualSheet(entries, this.assertions), pending: false, stale: true,
        error: "Источники превышают предел проверки фактов. Оригиналы сохранены в памяти; добавьте факты вручную." });
      return;
    }
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ ...this.view, pending: true, stale: true, error: null });
    try {
      const response = await this.request("/v1/facts", { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body, signal: abort.signal });
      if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json") || !response.body)
        throw new Error("failed");
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 4 * 1024 * 1024) throw new Error("large");
          chunks.push(value);
        }
      } finally { reader.releaseLock(); }
      if (epoch !== this.epoch) return;
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const value: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      if (!validateFactSheet(value) || value.units.length !== entries.reduce((count, entry) => count + entry.result.units.length +
            entry.result.gaps.filter((_, index) => Boolean(entry.overlays[`gap:${index}`]?.trim())).length, 0) ||
          value.units.some((unit) => !entries.some((entry) => entry.result.sourceId === unit.sourceId &&
            (entry.result.units.some((sourceUnit) => sourceUnit.id === unit.unitId) ||
             /^gap:(0|[1-9]\d*)$/.test(unit.unitId) && Boolean(entry.overlays[unit.unitId]?.trim()))))) throw new Error("invalid");
      const corrections = Object.fromEntries(Object.entries(this.corrections).filter(([id]) => value.facts.some((fact) => fact.id === id)));
      this.publish({ sheet: { ...value, facts: [...value.facts, ...this.assertions], userCorrections: corrections },
        pending: false, stale: false, error: null });
    } catch {
      if (epoch === this.epoch) this.publish({ ...this.view, sheet: this.view.sheet ?? manualSheet(entries, this.assertions), pending: false, stale: true,
        error: "Не удалось обновить факты. Принятые правки и исходники сохранены; повторите проверку." });
    } finally { if (this.abort === abort) this.abort = null; }
  }
}
