import type { ExtractResult } from "../contracts/generated/extract_result";
import { validateExtractResult } from "../contracts/validate";

export type ImportedSource = { result: ExtractResult; overlays: Record<string, string> };
export type ImportState = { entries: ImportedSource[]; selectedId: string | null; pending: boolean; error: string | null };

const maxSource = 6 * 1024 * 1024;
const maxSources = 10;
const maxOriginals = 32 * 1024 * 1024;
const maxExtracted = 8 * 1024 * 1024;
const maxResponse = 4 * 1024 * 1024;
const maxOverlay = 64 * 1024;
const maxOverlays = 1024 * 1024;
const encoder = new TextEncoder();
const fileTransports: Record<string, { name: string; kind: ExtractResult["sourceKind"]; mime: string }> = {
  ".pdf": { name: "source.pdf", kind: "pdf", mime: "application/pdf" },
  ".docx": { name: "source.docx", kind: "docx", mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  ".txt": { name: "source.txt", kind: "txt", mime: "text/plain" },
  ".md": { name: "source.md", kind: "markdown", mime: "text/markdown" },
  ".markdown": { name: "source.markdown", kind: "markdown", mime: "text/markdown" },
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorCode(value: unknown): string {
  if (!record(value) || !record(value.error) || typeof value.error.code !== "string") return "EXTRACT_FAILED";
  return value.error.code;
}

export function importError(code: string): string {
  const messages: Record<string, string> = {
    INPUT_TOO_LARGE: "Файл слишком большой. Выберите файл до 6 МБ.",
    EXTRACT_EMPTY: "Файл пустой. Выберите файл с текстом или вставьте текст вручную.",
    EXTRACT_UNSUPPORTED: "Формат не поддерживается. Используйте PDF, DOCX, UTF-8 TXT или Markdown. Старые DOC и DOCM не принимаются.",
    EXTRACT_ENCRYPTED: "Файл защищён паролем. Снимите защиту в исходной программе и выберите новую копию.",
    EXTRACT_ENCODING: "Не удалось прочитать текст как UTF-8. Сохраните его в UTF-8 и повторите.",
    EXTRACT_MALFORMED: "Файл повреждён или обрезан. Откройте его в исходной программе и сохраните новую копию.",
    EXTRACT_PAGE_LIMIT: "В PDF слишком много страниц. Предел — 40 страниц.",
    EXTRACT_TEXT_LIMIT: "Извлечено слишком много текста. Предел — 750 000 символов и 2 МБ UTF-8; сокращения без вашего выбора нет.",
    EXTRACT_UNIT_LIMIT: "В файле слишком много фрагментов. Разделите исходник и выберите часть отдельно.",
    EXTRACT_ARCHIVE_LIMIT: "DOCX превышает предел распаковки. Сохраните более компактную копию.",
    EXTRACT_UNSAFE_ARCHIVE: "Структура DOCX небезопасна или повреждена. Сохраните новую копию из редактора.",
    EXTRACT_UNSAFE_XML: "DOCX содержит неподдерживаемую структуру XML. Сохраните новую копию из редактора.",
    EXTRACT_EXTERNAL_LINK: "DOCX содержит внешние связанные объекты или неподдерживаемые адреса. Удалите их и сохраните новую копию.",
    EXTRACT_MEMORY_LIMIT: "Обработка превысила предел памяти. Упростите файл и повторите.",
    EXTRACT_MONITOR_UNAVAILABLE: "Контроль памяти недоступен. Перезапустите локальный сервис и повторите.",
    OPERATION_TIMEOUT: "Чтение заняло слишком много времени. Упростите файл и повторите.",
    BUSY: "Другая операция ещё выполняется. Дождитесь её завершения или отмените импорт.",
    IMPORT_TOTAL_LIMIT: "В памяти уже много источников. Предел — 10 файлов, 32 МБ оригиналов и 8 МБ извлечённого текста. Очистите импорт перед новой загрузкой.",
    OVERLAY_LIMIT: "Исправление слишком длинное. Предел — 64 КБ на поле и 1 МБ на все исправления.",
    EXTRACT_RESPONSE_LIMIT: "Ответ извлечения слишком большой. Выберите более короткий источник.",
    IMPORT_CHANGED_EXTRACTION: "Этот же файл прочитан иначе, а исправления ещё не сохранены. Оставлен прежний источник; очистите его перед повторным импортом.",
  };
  return messages[code] ?? "Не удалось прочитать источник. Проверьте файл и повторите.";
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes));
  return Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, "0")).join("");
}

async function boundedJson(response: Response): Promise<unknown> {
  if (!response.headers.get("content-type")?.startsWith("application/json") || !response.body) throw new Error("invalid response");
  const declared = response.headers.get("content-length");
  if (declared !== null && (!Number.isFinite(Number(declared)) || Number(declared) > maxResponse))
    throw new Error("response limit");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > maxResponse) throw new Error("response limit");
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel();
    throw error;
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(joined)) as unknown;
}

export class ImportWorkflow {
  private epoch = 0;
  private abort: AbortController | null = null;
  private originals = new Map<string, Uint8Array>();
  private closed = false;
  state: ImportState = { entries: [], selectedId: null, pending: false, error: null };
  constructor(private readonly onChange: (state: ImportState) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  original(id: string): Uint8Array | null {
    const bytes = this.originals.get(id);
    return bytes ? Uint8Array.from(bytes) : null;
  }

  select(id: string): void {
    if (!this.state.entries.some((entry) => entry.result.sourceId === id)) return;
    this.publish({ ...this.state, selectedId: id });
  }

  overlay(sourceId: string, target: string, text: string): void {
    const source = this.state.entries.find((entry) => entry.result.sourceId === sourceId);
    if (!source) return;
    const valid = target.startsWith("unit:")
      ? source.result.units.some((unit) => `unit:${unit.id}` === target)
      : /^gap:(0|[1-9]\d*)$/.test(target) && Number(target.slice(4)) < source.result.gaps.length;
    if (!valid) return;
    const size = encoder.encode(text).length;
    const other = this.state.entries.reduce((total, entry) => total + Object.entries(entry.overlays).reduce((part, [key, value]) =>
      part + (entry.result.sourceId === sourceId && key === target ? 0 : encoder.encode(value).length), 0), 0);
    if (size > maxOverlay || other + size > maxOverlays) {
      this.publish({ ...this.state, error: importError("OVERLAY_LIMIT") });
      return;
    }
    const entries = this.state.entries.map((entry) => entry.result.sourceId === sourceId
      ? { ...entry, overlays: { ...entry.overlays, [target]: text } } : entry);
    this.publish({ ...this.state, entries, error: null });
  }

  cancel(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    this.publish({ ...this.state, pending: false, error: null });
  }

  clear(): void {
    this.cancel();
    this.originals.clear();
    this.publish({ entries: [], selectedId: null, pending: false, error: null });
  }

  close(): void {
    this.closed = true;
    this.epoch += 1;
    this.abort?.abort();
    this.originals.clear();
  }

  async file(file: File): Promise<void> {
    this.cancel();
    const epoch = this.epoch;
    if (!file.size || file.size > maxSource) {
      this.fail(epoch, file.size ? "INPUT_TOO_LARGE" : "EXTRACT_EMPTY");
      return;
    }
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (epoch !== this.epoch || this.closed) return;
      await this.run(bytes, file.name, false, epoch);
    } catch {
      this.fail(epoch, "EXTRACT_FAILED");
    }
  }

  async paste(text: string): Promise<void> {
    this.cancel();
    const epoch = this.epoch;
    if ([...text].some((character) => character.length === 1 && character.charCodeAt(0) >= 0xd800 && character.charCodeAt(0) <= 0xdfff)) {
      this.fail(epoch, "EXTRACT_ENCODING");
      return;
    }
    await this.run(new TextEncoder().encode(text), "pasted.txt", true, epoch);
  }

  private async run(bytes: Uint8Array, name: string, pasted: boolean, epoch: number): Promise<void> {
    if (!bytes.length || bytes.length > maxSource) {
      this.fail(epoch, bytes.length ? "INPUT_TOO_LARGE" : "EXTRACT_EMPTY");
      return;
    }
    const abort = new AbortController();
    const suffix = name.slice(name.lastIndexOf(".")).toLowerCase();
    const transport = pasted ? { name: "pasted.txt", kind: "paste", mime: "text/plain" }
      : fileTransports[suffix] ?? { name: "source.unsupported", kind: null, mime: null };
    this.abort = abort;
    this.publish({ ...this.state, pending: true, error: null });
    try {
      const body = new FormData();
      body.append(pasted ? "paste" : "file", new Blob([Uint8Array.from(bytes)]), transport.name);
      const response = await this.request("/v1/extract", { method: "POST", credentials: "same-origin",
        cache: "no-store", body, signal: abort.signal });
      const value = await boundedJson(response);
      if (epoch !== this.epoch || this.closed) return;
      if (!response.ok) { this.fail(epoch, errorCode(value)); return; }
      if (!validateExtractResult(value) || value.byteLength !== bytes.length || value.byteSha256 !== await sha256(bytes) ||
          value.byteRef !== `memory:sha256:${value.byteSha256}` || value.originalName !== transport.name ||
          value.sourceId !== `source_${value.byteSha256.slice(0, 24)}` || value.sourceKind !== transport.kind ||
          value.mimeType !== transport.mime) {
        this.fail(epoch, "EXTRACT_FAILED");
        return;
      }
      if (epoch !== this.epoch || this.closed) return;
      const previous = this.state.entries.find((entry) => entry.result.sourceId === value.sourceId);
      const compatible = previous !== undefined && previous.result.sourceKind === value.sourceKind &&
        previous.result.parser === value.parser && previous.result.parserVersion === value.parserVersion &&
        previous.result.mimeType === value.mimeType && previous.result.pageCount === value.pageCount &&
        JSON.stringify(previous.result.units) === JSON.stringify(value.units) &&
        JSON.stringify(previous.result.gaps) === JSON.stringify(value.gaps) &&
        JSON.stringify(previous.result.links) === JSON.stringify(value.links);
      if (previous && !compatible && Object.values(previous.overlays).some((text) => text.length > 0)) {
        this.fail(epoch, "IMPORT_CHANGED_EXTRACTION");
        return;
      }
      const retained = this.state.entries.filter((item) => item.result.sourceId !== value.sourceId);
      const originalBytes = retained.reduce((total, entry) => total + entry.result.byteLength, 0) + bytes.length;
      const extractedBytes = retained.reduce((total, entry) => total + entry.result.units.reduce((sum, unit) => sum + encoder.encode(unit.text).length, 0), 0)
        + value.units.reduce((sum, unit) => sum + encoder.encode(unit.text).length, 0);
      if (retained.length >= maxSources || originalBytes > maxOriginals || extractedBytes > maxExtracted) {
        this.fail(epoch, "IMPORT_TOTAL_LIMIT");
        return;
      }
      const entry: ImportedSource = { result: { ...value, originalName: name }, overlays: compatible ? previous.overlays : {} };
      this.originals.set(value.sourceId, Uint8Array.from(bytes));
      this.publish({ entries: [...retained, entry],
        selectedId: value.sourceId, pending: false, error: null });
    } catch (error) {
      this.fail(epoch, error instanceof Error && error.message === "response limit" ? "EXTRACT_RESPONSE_LIMIT" : "EXTRACT_FAILED");
    } finally {
      if (epoch === this.epoch) this.abort = null;
    }
  }

  private fail(epoch: number, code: string): void {
    if (epoch === this.epoch && !this.closed)
      this.publish({ ...this.state, pending: false, error: importError(code) });
  }

  private publish(state: ImportState): void {
    if (this.closed) return;
    this.state = state;
    this.onChange(state);
  }
}
