import { Unzip, UnzipInflate } from "fflate";
import type { PrepareRequest } from "../contracts/generated/prepare_request";
import type { RenderRequest } from "../contracts/generated/render_request";
import { validateRenderRequest } from "../contracts/validate";

const maxArchive = 16 * 1024 * 1024;
const limits: Record<string, number> = { "resume.docx": 8 * 1024 * 1024, "resume.pdf": 12 * 1024 * 1024, "render.json": 8192 };
const names = Object.keys(limits);
const privateOutputMessages: Record<string, string> = {
  PRIVATE_OUTPUT_IDENTITY: "В данных кандидата есть контакт, возраст или данные сайта вакансий. Исправьте имя или должность и повторите сборку.",
  PRIVATE_OUTPUT_PROFILE: "В видимом разделе «О себе» есть контакт, возраст или данные сайта вакансий. Исправьте текст и повторите сборку.",
  PRIVATE_OUTPUT_JOB: "В видимом разделе работы есть контакт, возраст или данные сайта вакансий. Исправьте текст или поля работы и повторите сборку.",
  PRIVATE_OUTPUT_FOCUS: "В видимом разделе специализации есть контакт, возраст или данные сайта вакансий. Исправьте поле и повторите сборку.",
  PRIVATE_OUTPUT_SIDEBAR: "В видимом боковом разделе есть контакт, возраст или данные сайта вакансий. Исправьте поле и повторите сборку.",
  PRIVATE_OUTPUT_SKILLS: "В видимом разделе навыков есть контакт, возраст или данные сайта вакансий. Исправьте поле и повторите сборку.",
  PRIVATE_OUTPUT_ACHIEVEMENTS: "В видимом разделе достижений есть контакт, возраст или данные сайта вакансий. Исправьте текст и повторите сборку.",
  PRIVATE_OUTPUT_FOOTER: "В видимом нижнем поле есть контакт, возраст или данные сайта вакансий. Исправьте текст и повторите сборку.",
};

export class PrivateOutputError extends Error {}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function archiveEntries(bytes: Uint8Array): Map<string, { expanded: number; crc: number }> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const invalid = () => { throw new Error("invalid archive directory"); };
  const uint16 = (offset: number) => view.getUint16(offset, true);
  const uint32 = (offset: number) => view.getUint32(offset, true);
  const eocd = bytes.length - 22;
  if (eocd < 0 || uint32(eocd) !== 0x06054b50 || uint16(eocd + 4) !== 0 || uint16(eocd + 6) !== 0 ||
      uint16(eocd + 8) !== names.length || uint16(eocd + 10) !== names.length || uint16(eocd + 20) !== 0) invalid();
  const centralSize = uint32(eocd + 12);
  const centralOffset = uint32(eocd + 16);
  if (centralOffset + centralSize !== eocd) invalid();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const found = new Set<string>();
  const entries = new Map<string, { expanded: number; crc: number }>();
  let central = centralOffset;
  let local = 0;
  for (let index = 0; index < names.length; index += 1) {
    if (central + 46 > eocd || uint32(central) !== 0x02014b50) invalid();
    const flags = uint16(central + 8);
    const method = uint16(central + 10);
    const crc = uint32(central + 16);
    const compressed = uint32(central + 20);
    const expanded = uint32(central + 24);
    const nameLength = uint16(central + 28);
    const extraLength = uint16(central + 30);
    const commentLength = uint16(central + 32);
    const next = central + 46 + nameLength + extraLength + commentLength;
    if (next > eocd || flags !== 0 || method !== 8 || extraLength !== 0 || commentLength !== 0 ||
        uint16(central + 34) !== 0 || uint16(central + 36) !== 0 || uint32(central + 42) !== local) invalid();
    const name = decoder.decode(bytes.subarray(central + 46, central + 46 + nameLength));
    if (!Object.hasOwn(limits, name) || found.has(name) || expanded > limits[name]!) invalid();
    found.add(name);
    entries.set(name, { expanded, crc });
    if (local + 30 > centralOffset || uint32(local) !== 0x04034b50 || uint16(local + 6) !== flags ||
        uint16(local + 8) !== method || uint32(local + 14) !== crc || uint32(local + 18) !== compressed ||
        uint32(local + 22) !== expanded || uint16(local + 26) !== nameLength || uint16(local + 28) !== 0 ||
        !bytes.subarray(local + 30, local + 30 + nameLength).every((part, offset) => part === bytes[central + 46 + offset])) invalid();
    local += 30 + nameLength + compressed;
    if (local > centralOffset) invalid();
    central = next;
  }
  if (central !== eocd || local !== centralOffset || found.size !== names.length) invalid();
  return entries;
}

export type Rendered = { request: RenderRequest; pdf: Uint8Array; docx: Uint8Array };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes));
  return Array.from(new Uint8Array(digest), (part) => part.toString(16).padStart(2, "0")).join("");
}

async function requestJson(path: string, body: unknown, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), ...(signal ? { signal } : {}) });
  if (!response.ok) {
    if (response.headers.get("content-type")?.startsWith("application/json")) {
      const payload: unknown = await response.json();
      const error = record(payload) ? payload.error : null;
      const code = record(error) && typeof error.code === "string" ? error.code : "";
      if (Object.hasOwn(privateOutputMessages, code)) throw new PrivateOutputError(privateOutputMessages[code]);
    }
    throw new Error("request failed");
  }
  if (!response.headers.get("content-type")?.startsWith("application/json")) throw new Error("request failed");
  return await response.json() as unknown;
}

export async function prepare(input: PrepareRequest, signal?: AbortSignal): Promise<RenderRequest> {
  const result = await requestJson("/v1/prepare-render", input, signal);
  if (!await validateRenderRequest(result)) throw new Error("invalid preparation");
  return result as RenderRequest;
}

async function unzipResponse(response: Response, signal?: AbortSignal): Promise<Record<string, Uint8Array>> {
  if (!response.ok || response.headers.get("content-type")?.split(";")[0] !== "application/zip" || !response.body)
    throw new Error("invalid render response");
  const declared = Number(response.headers.get("content-length"));
  if (declared && (!Number.isFinite(declared) || declared > maxArchive)) throw new Error("archive too large");
  const chunks = new Map<string, Uint8Array[]>();
  const sizes = new Map<string, number>();
  const finished = new Set<string>();
  let failure: Error | null = null;
  const unzip = new Unzip((file) => {
    const limit = Object.hasOwn(limits, file.name) ? limits[file.name] : undefined;
    if (limit === undefined || chunks.has(file.name) || file.originalSize !== undefined && file.originalSize > limit) {
      failure = new Error("unexpected archive entry");
      return;
    }
    chunks.set(file.name, []);
    sizes.set(file.name, 0);
    file.ondata = (error, chunk, final) => {
      if (error || failure) { failure = new Error("invalid archive entry"); return; }
      const size = (sizes.get(file.name) ?? 0) + chunk.length;
      if (size > limit) { failure = new Error("archive entry too large"); return; }
      sizes.set(file.name, size);
      chunks.get(file.name)?.push(chunk);
      if (final) finished.add(file.name);
    };
    try { file.start(); } catch { failure = new Error("unsupported archive compression"); }
  });
  unzip.register(UnzipInflate);
  const reader = response.body.getReader();
  let total = 0;
  const archiveChunks: Uint8Array[] = [];
  try {
    while (true) {
      if (signal?.aborted) throw new Error("render cancelled");
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > maxArchive) throw new Error("archive too large");
      archiveChunks.push(value);
      for (let offset = 0; offset < value.length; offset += 4096) {
        if (signal?.aborted) throw new Error("render cancelled");
        unzip.push(value.subarray(offset, offset + 4096));
        if (failure) throw failure;
      }
    }
    unzip.push(new Uint8Array(0), true);
    if (failure) throw failure;
  } catch (error) {
    await reader.cancel();
    throw error;
  } finally { reader.releaseLock(); }
  const archive = new Uint8Array(total);
  let archiveOffset = 0;
  for (const chunk of archiveChunks) { archive.set(chunk, archiveOffset); archiveOffset += chunk.length; }
  const directory = archiveEntries(archive);
  if (chunks.size !== names.length || names.some((name) => !finished.has(name))) throw new Error("incomplete archive");
  const result: Record<string, Uint8Array> = {};
  for (const name of names) {
    const size = sizes.get(name) ?? 0;
    const joined = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks.get(name) ?? []) { joined.set(chunk, offset); offset += chunk.length; }
    const entry = directory.get(name);
    if (!entry || joined.length !== entry.expanded || crc32(joined) !== entry.crc) throw new Error("invalid archive entry");
    result[name] = joined;
  }
  return result;
}

export async function render(request: RenderRequest, signal?: AbortSignal): Promise<Rendered> {
  const response = await fetch("/v1/render", { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), ...(signal ? { signal } : {}) });
  const entries = await unzipResponse(response, signal);
  const docx = entries["resume.docx"];
  const pdf = entries["resume.pdf"];
  const metadataBytes = entries["render.json"];
  if (!docx || !pdf || !metadataBytes || docx.length < 4 || pdf.length < 4 ||
      docx[0] !== 0x50 || docx[1] !== 0x4b || new TextDecoder().decode(pdf.subarray(0, 4)) !== "%PDF")
    throw new Error("invalid document bytes");
  let metadata: unknown;
  try { metadata = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(metadataBytes)) as unknown; }
  catch { throw new Error("invalid render metadata"); }
  const identity = request.snapshot;
  if (!record(metadata) || metadata.snapshotId !== identity.id || metadata.projectRevision !== identity.projectRevision ||
      metadata.snapshotSha256 !== identity.snapshotSha256 || metadata.templateId !== identity.templateId ||
      metadata.templateVersion !== identity.templateVersion || metadata.templatePackageSha256 !== identity.templatePackageSha256 ||
      metadata.rendererVersion !== identity.rendererVersion || metadata.rendererSha256 !== identity.rendererSha256 ||
      !Number.isInteger(metadata.pageCount) || Number(metadata.pageCount) < 1 || Number(metadata.pageCount) > 30 ||
      metadata.docxSha256 !== await sha256(docx) || metadata.pdfSha256 !== await sha256(pdf) ||
      !record(metadata.capabilities) || metadata.capabilities.editableDocx !== true ||
      metadata.capabilities.pdfDerivedFromDocx !== true || metadata.capabilities.embeddedPdfFonts !== true)
    throw new Error("render metadata mismatch");
  return { request, pdf, docx };
}
