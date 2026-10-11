import { Inflate, zipSync } from "fflate";

const MAX_ARCHIVE = 64 * 1024 * 1024;
const MAX_TOTAL = 60 * 1024 * 1024;
const MAX_ENTRY = 32 * 1024 * 1024;
const MAX_ENTRIES = 48;
const MAX_RATIO = 200;
const decoder = new TextDecoder("utf-8", { fatal: true });

type Entry = { name: string; expanded: number; compressed: number; crc: number; method: number; dataStart: number };

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function safeArchivePath(path: string): boolean {
  return path.length > 0 && path.length <= 240 && !path.startsWith("/") && !path.includes("\\") &&
    !path.includes(":") && !/[\u0000-\u001f\u007f]/.test(path) && path.split("/").every((part) =>
      part.length > 0 && part !== "." && part !== ".." && !part.endsWith(".") && !part.endsWith(" "));
}

function inspect(bytes: Uint8Array): Entry[] {
  const bad = (): never => { throw new Error("Invalid project ZIP structure."); };
  if (bytes.length < 22 || bytes.length > MAX_ARCHIVE) bad();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const u16 = (offset: number) => view.getUint16(offset, true);
  const u32 = (offset: number) => view.getUint32(offset, true);
  const end = bytes.length - 22;
  if (u32(end) !== 0x06054b50 || u16(end + 4) !== 0 || u16(end + 6) !== 0 ||
      u16(end + 20) !== 0 || u16(end + 8) !== u16(end + 10)) bad();
  const count = u16(end + 10);
  if (count < 2 || count > MAX_ENTRIES) bad();
  const centralSize = u32(end + 12);
  const centralOffset = u32(end + 16);
  if (centralOffset + centralSize !== end) bad();
  const found = new Set<string>();
  const entries: Entry[] = [];
  let central = centralOffset;
  let local = 0;
  let expandedTotal = 0;
  for (let index = 0; index < count; index += 1) {
    if (central + 46 > end || u32(central) !== 0x02014b50) bad();
    const flags = u16(central + 8);
    const method = u16(central + 10);
    const crc = u32(central + 16);
    const compressed = u32(central + 20);
    const expanded = u32(central + 24);
    const nameLength = u16(central + 28);
    const extraLength = u16(central + 30);
    const commentLength = u16(central + 32);
    const next = central + 46 + nameLength + extraLength + commentLength;
    if (next > end || flags !== 0 || ![0, 8].includes(method) || extraLength !== 0 || commentLength !== 0 ||
        u16(central + 34) !== 0 || u16(central + 36) !== 0 ||
        (u32(central + 38) >>> 16 & 0xf000) === 0xa000 || u32(central + 42) !== local ||
        nameLength === 0 || expanded > MAX_ENTRY || compressed > MAX_ARCHIVE ||
        (method === 0 && compressed !== expanded) ||
        (compressed === 0 ? expanded !== 0 : expanded / compressed > MAX_RATIO)) bad();
    let name = "";
    try { name = decoder.decode(bytes.subarray(central + 46, central + 46 + nameLength)); }
    catch { bad(); }
    if (!safeArchivePath(name) || found.has(name.normalize("NFC").toLowerCase()) ||
        ["__proto__", "prototype", "constructor"].some((part) => name.split("/").includes(part))) bad();
    found.add(name.normalize("NFC").toLowerCase());
    if (local + 30 + nameLength > centralOffset || u32(local) !== 0x04034b50 ||
        u16(local + 6) !== flags || u16(local + 8) !== method || u32(local + 14) !== crc ||
        u32(local + 18) !== compressed || u32(local + 22) !== expanded ||
        u16(local + 26) !== nameLength || u16(local + 28) !== 0 ||
        !bytes.subarray(local + 30, local + 30 + nameLength).every((part, offset) => part === bytes[central + 46 + offset])) bad();
    const dataStart = local + 30 + nameLength;
    local = dataStart + compressed;
    if (local > centralOffset) bad();
    expandedTotal += expanded;
    if (expandedTotal > MAX_TOTAL) bad();
    entries.push({ name, expanded, compressed, crc, method, dataStart });
    central = next;
  }
  if (central !== end || local !== centralOffset) bad();
  return entries;
}

export function readZip(bytes: Uint8Array): Map<string, Uint8Array> {
  const directory = inspect(bytes);
  const result = new Map<string, Uint8Array>();
  for (const entry of directory) {
    const compressed = bytes.subarray(entry.dataStart, entry.dataStart + entry.compressed);
    const data = new Uint8Array(entry.expanded);
    let written = 0;
    if (entry.method === 0) data.set(compressed);
    else {
      try {
        const inflater = new Inflate((chunk) => {
          if (chunk.length > entry.expanded - written) throw new Error("Project ZIP entry exceeds its declared size.");
          data.set(chunk, written);
          written += chunk.length;
        });
        // Small compressed chunks bound work and temporary output before each size check.
        for (let offset = 0; offset < compressed.length; offset += 1024) {
          const end = Math.min(offset + 1024, compressed.length);
          inflater.push(compressed.subarray(offset, end), end === compressed.length);
        }
      } catch { throw new Error("Project ZIP cannot be decompressed within its declared size."); }
      if (written !== entry.expanded) throw new Error("Project ZIP entry size is false.");
    }
    if (crc32(data) !== entry.crc) throw new Error("Project ZIP entry is corrupt.");
    result.set(entry.name, data);
  }
  return result;
}

export function writeZip(entries: Map<string, Uint8Array>): Uint8Array {
  if (entries.size < 2 || entries.size > MAX_ENTRIES) throw new Error("Project has too many archive entries.");
  const input: Record<string, Uint8Array> = Object.create(null) as Record<string, Uint8Array>;
  let total = 0;
  const names = new Set<string>();
  for (const [name, bytes] of entries) {
    if (!safeArchivePath(name) || names.has(name.normalize("NFC").toLowerCase()) || bytes.length > MAX_ENTRY)
      throw new Error("Invalid project archive entry.");
    names.add(name.normalize("NFC").toLowerCase());
    total += bytes.length;
    if (total > MAX_TOTAL) throw new Error("Project is too large to save.");
    input[name] = bytes;
  }
  const output = zipSync(input, { level: 0 });
  inspect(output);
  return output;
}
