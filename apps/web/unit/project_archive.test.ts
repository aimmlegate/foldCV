import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { zipSync } from "fflate";
import renderFixture from "../../../contracts/examples/render_request.json" with { type: "json" };
import factRequest from "../../../contracts/examples/fact_request.json" with { type: "json" };
import sheetFixture from "../../../contracts/examples/fact_sheet.json" with { type: "json" };
import type { FactSheet } from "../src/contracts/generated/fact_sheet";
import type { ExtractResult } from "../src/contracts/generated/extract_result";
import { validateExtractResult, validateFactSheet } from "../src/contracts/validate";
import { adaptWorking, emptyManualInput } from "../src/facts/working";
import type { ManualInput, WorkingDraft } from "../src/facts/working";
import { editorReducer, initialEditorState } from "../src/editor/state";
import type { EditorState } from "../src/editor/state";
import { exportReadiness } from "../src/preview/readiness";
import { syntheticProject, syntheticSourceBytes } from "../src/editor/example";
import { openProject, saveProject } from "../src/project/archive";
import type { ArchiveInput } from "../src/project/archive";
import { readZip, writeZip } from "../src/project/zip";

const encoder = new TextEncoder();
const original = encoder.encode("Skills: Python, Docker\nAcme Engineer 2020-2022\n");
function hash(bytes: Uint8Array): string { return createHash("sha256").update(bytes).digest("hex"); }
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function parsed(bytes: Uint8Array | undefined): Record<string, unknown> {
  assert.ok(bytes);
  const value: unknown = JSON.parse(new TextDecoder().decode(bytes)) as unknown;
  assert.ok(record(value));
  return value;
}
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (typeof value === "object" && value !== null)
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b, "en"))
      .map(([key, part]) => [key, ordered(part)]));
  return value;
}
function base(): ArchiveInput {
  return { editor: editorReducer(initialEditorState, { type: "loadExample", loadId: "before-open" }),
    imports: { state: { entries: [], selectedId: null, pending: false, error: null }, originals: {} },
    projectOriginals: {}, legacy: null, trustedAssets: null,
    facts: { view: { sheet: null, pending: false, stale: false, error: null }, assertions: [], corrections: {} },
    manualForm: structuredClone(emptyManualInput), assertionDraft: "", factEdits: {}, rewriteInstruction: "", render: null };
}
async function altered(bytes: Uint8Array, modify: (files: Map<string, Uint8Array>) => void,
                       repairHash = true): Promise<Uint8Array> {
  const files = readZip(bytes);
  modify(files);
  if (repairHash) {
    const raw: unknown = JSON.parse(new TextDecoder().decode(files.get("manifest.json")));
    assert.ok(typeof raw === "object" && raw !== null && "entries" in raw && Array.isArray(raw.entries));
    const entries: unknown[] = raw.entries;
    for (const item of entries) {
      if (typeof item !== "object" || item === null || !("path" in item) || typeof item.path !== "string") continue;
      const data = files.get(item.path);
      if (data && "sha256" in item && "uncompressedSize" in item) {
        item.sha256 = hash(data); item.uncompressedSize = data.length;
      }
    }
    files.set("manifest.json", encoder.encode(JSON.stringify(raw)));
  }
  return writeZip(files);
}

test("accepted editor, pending drafts, review and undo round trip without inference", async () => {
  const input = base();
  let state = input.editor;
  state = editorReducer(state, { type: "review", id: "profile" });
  state = editorReducer(state, { type: "draft", id: "profile", text: "Accepted manual profile" });
  state = editorReducer(state, { type: "apply", id: "profile" });
  state = editorReducer(state, { type: "draft", id: "profile", text: "Unapplied next value" });
  state = editorReducer(state, { type: "visible", id: "job_2_prose" });
  input.editor = state;
  const bytes = await saveProject(input);
  const opened = await openProject(bytes);
  assert.notEqual(opened.editor.loadId, state.loadId);
  assert.equal(opened.editor.sourceIntegrity, null);
  assert.deepEqual(opened.editor.project, state.project);
  assert.deepEqual(opened.editor.undo, state.undo);
  assert.deepEqual(opened.editor.drafts, state.drafts);
  assert.deepEqual(opened.editor.presentation, state.presentation);
  const workspaceText = new TextDecoder().decode(readZip(bytes).get("workspace.json"));
  assert.equal(workspaceText.includes("loadId"), false);
  assert.equal(workspaceText.includes("sourceIntegrity"), false);
  const undone = editorReducer(opened.editor, { type: "undo", id: "profile" });
  assert.equal(undone.project?.views.find((block) => block.id === "profile")?.state.text,
    "Engineer with service experience.");
  assert.equal(undone.drafts.profile, "Unapplied next value");
});

test("partial failed import and unapplied manual forms save without an editor", async () => {
  const input = base();
  input.editor = { ...initialEditorState, sourceText: "Unsent paste", dirty: true };
  input.manualForm = { ...emptyManualInput, title: "Pending title", education: "Pending education" };
  input.assertionDraft = "Unapplied assertion";
  input.factEdits = { source_fact: "Unapplied correction" };
  const opened = await openProject(await saveProject(input));
  assert.equal(opened.editor.project, null);
  assert.equal(opened.editor.sourceText, "Unsent paste");
  assert.deepEqual(opened.manualForm, input.manualForm);
  assert.equal(opened.assertionDraft, input.assertionDraft);
  assert.deepEqual(opened.factEdits, input.factEdits);
});

test("standalone warning review survives v4 reopen; older v4 defaults and malformed entries fail", async () => {
  const input = base();
  const warning = exportReadiness(input.editor).unacknowledged[0];
  assert.ok(warning);
  input.editor = editorReducer(input.editor, { type: "coverageAcknowledge",
    issueId: warning.id, dependency: warning.dependency });
  const bytes = await saveProject(input);
  const opened = await openProject(bytes);
  assert.deepEqual(opened.editor.standaloneAcknowledgments, input.editor.standaloneAcknowledgments);
  assert.equal(exportReadiness(opened.editor).review?.warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  const priorV4 = await altered(bytes, (files) => {
    const workspace = parsed(files.get("workspace.json"));
    assert.ok(record(workspace.editor));
    delete workspace.editor.standaloneAcknowledgments;
    delete workspace.editor.standaloneDecisions;
    files.set("workspace.json", encoder.encode(JSON.stringify(workspace)));
  });
  assert.deepEqual((await openProject(priorV4)).editor.standaloneAcknowledgments, []);
  assert.deepEqual((await openProject(priorV4)).editor.standaloneDecisions, []);
  const malformed = await altered(bytes, (files) => {
    const workspace = parsed(files.get("workspace.json"));
    assert.ok(record(workspace.editor));
    workspace.editor.standaloneAcknowledgments = [{ issueId: warning.id, dependency: warning.dependency,
      bypass: true }];
    files.set("workspace.json", encoder.encode(JSON.stringify(workspace)));
  });
  await assert.rejects(openProject(malformed), /workspace/);
  const malformedDecision = await altered(bytes, (files) => {
    const workspace = parsed(files.get("workspace.json"));
    assert.ok(record(workspace.editor));
    workspace.editor.standaloneDecisions = [{ targetKind: "fact", targetId: "fact_metric",
      disposition: "excluded", reason: "", dependency: "old", bypass: true }];
    files.set("workspace.json", encoder.encode(JSON.stringify(workspace)));
  });
  await assert.rejects(openProject(malformedDecision), /workspace/);
});

test("reasoned standalone fact exclusion survives archive reopen", async () => {
  const input = base();
  const project = input.editor.project!;
  const changed = { ...project, views: project.views.map((block) => block.id === "job_1_prose" ?
    { ...block, state: { ...block.state, factIds: [], factRevisions: {} } } : block) };
  let state: EditorState = { ...input.editor, project: changed };
  const missing = exportReadiness(state).blockers.find((item) => item.code === "MISSING_ESSENTIAL");
  assert.ok(missing?.factId);
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: missing.factId,
    disposition: "excluded", reason: "Selected resume omits this fact", dependency: missing.dependency });
  input.editor = state;
  const opened = await openProject(await saveProject(input));
  assert.deepEqual(opened.editor.standaloneDecisions, state.standaloneDecisions);
  assert.equal(exportReadiness(opened.editor).blockers.some((item) => item.code === "MISSING_ESSENTIAL"), false);
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Changed selected prose." });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  input.editor = state;
  const edited = await openProject(await saveProject(input));
  assert.equal(edited.editor.standaloneDecisions.length, 0);
  assert.equal(edited.editor.undo.job_1_prose?.standaloneDecisions.length, 1);
  const undone = editorReducer(edited.editor, { type: "undo", id: "job_1_prose" });
  assert.equal(undone.standaloneDecisions[0]?.reason, "Selected resume omits this fact");
});

test("standalone review checkpoint restores only matching warnings after reopen and undo", async () => {
  const input = base();
  const warning = exportReadiness(input.editor).unacknowledged.find((item) => item.blockId === "job_1_prose");
  assert.ok(warning);
  let state = editorReducer(input.editor, { type: "coverageAcknowledge",
    issueId: warning.id, dependency: warning.dependency });
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Changed job prose." });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  assert.equal(exportReadiness(state).review?.warnings.find((item) => item.id === warning.id)?.acknowledged, false);
  input.editor = state;
  const reopened = await openProject(await saveProject(input));
  assert.equal(reopened.editor.undo.job_1_prose?.standaloneAcknowledgments.length, 1);
  const restored = editorReducer(reopened.editor, { type: "undo", id: "job_1_prose" });
  assert.equal(exportReadiness(restored).review?.warnings.find((item) => item.id === warning.id)?.acknowledged, true);
});

test("complete imported working sheet, original and manual description remain exact", async () => {
  const rawResult: unknown = structuredClone(factRequest.sources[0]?.result);
  const rawSheet: unknown = structuredClone(sheetFixture);
  assert.ok(validateExtractResult(rawResult) && validateFactSheet(rawSheet));
  const result = rawResult as ExtractResult;
  const sheet = rawSheet as FactSheet;
  const manual: ManualInput = { ...emptyManualInput, name: "Alex Example", title: "Engineer", asOf: "2026-10-11",
    language: "en", employment: [{ id: "job_manual", employer: "Example Works", role: "Developer", start: "2021",
      end: "2024", description: "Kept exact manual text.", subprojects: [] }] };
  const working: WorkingDraft = { transportVersion: 1, sources: [{ entry: { result, overlays: { "unit:unit_1": "Corrected" } },
    originalBytes: original }], sheet, priorSheet: null, sourceReviewStale: true, manual, draft: null };
  const input = base();
  input.editor = editorReducer(initialEditorState, { type: "loadImported", loadId: "old-import",
    ...adaptWorking(working), working });
  input.imports = { state: { entries: [working.sources[0]!.entry], selectedId: result.sourceId,
    pending: false, error: null }, originals: { [result.sourceId]: original } };
  input.facts = { view: { sheet, pending: false, stale: true, error: null }, assertions: [], corrections: {} };
  input.manualForm = manual;
  const opened = await openProject(await saveProject(input));
  assert.deepEqual(opened.editor.working, working);
  assert.deepEqual(opened.imports.originals[result.sourceId], original);
  assert.deepEqual(opened.facts.view.sheet, sheet);
  assert.equal(opened.editor.project?.facts.find((fact) => fact.id === "fact_user_manual_job_job_manual")?.kind, "text");
});

test("explicit project save keeps hidden original bytes without runtime load ID or render cache", async () => {
  const input = base();
  input.editor = { ...input.editor, loadId: "synthetic-startup-secret-0123456789" };
  const source = input.editor.project?.sources[0];
  assert.ok(source);
  const saved = await saveProject(input);
  const files = readZip(saved);
  assert.deepEqual(files.get(source.byteRef), syntheticSourceBytes);
  assert.match(new TextDecoder().decode(files.get(source.byteRef)), /Earlier education detail kept in the archive/);
  assert.equal(files.has("renders/preview.pdf"), false);
  assert.equal(files.has("renders/resume.docx"), false);
  const payload = [...files.entries()].filter(([path]) => path.endsWith(".json"))
    .map(([, bytes]) => new TextDecoder().decode(bytes)).join("\n");
  for (const forbidden of ["synthetic-startup-secret-0123456789", "foldcv_session=", "CODEX_HOME",
    "/private/var/folders/", "render-input.json"]) assert.equal(payload.includes(forbidden), false, forbidden);
  const opened = await openProject(saved);
  assert.deepEqual(opened.projectOriginals[source.id], syntheticSourceBytes);
  assert.equal(opened.render, null);
});

test("wrong hash and nested runtime injection fail before a replacement is available", async () => {
  const bytes = await saveProject(base());
  const wrongHash = await altered(bytes, (files) => files.set("workspace.json", encoder.encode("{}")), false);
  await assert.rejects(openProject(wrongHash), /hash/);
  const badUndo = await altered(bytes, (files) => {
    const raw: unknown = JSON.parse(new TextDecoder().decode(files.get("workspace.json")));
    assert.ok(typeof raw === "object" && raw !== null && "editor" in raw &&
      typeof raw.editor === "object" && raw.editor !== null && "undo" in raw.editor);
    raw.editor.undo = { profile: { token: "secret" } };
    files.set("workspace.json", encoder.encode(JSON.stringify(raw)));
  });
  await assert.rejects(openProject(badUndo), /workspace/);
  const invalidDetails = await altered(bytes, (files) => {
    const raw: unknown = JSON.parse(new TextDecoder().decode(files.get("workspace.json")));
    assert.ok(typeof raw === "object" && raw !== null && "editor" in raw &&
      typeof raw.editor === "object" && raw.editor !== null);
    Object.assign(raw.editor, { rewriteIssueDetails: { profile: [{ blockId: "profile", code: "UNKNOWN",
      factId: "fact_metric", message: "bad" }] } });
    files.set("workspace.json", encoder.encode(JSON.stringify(raw)));
  });
  await assert.rejects(openProject(invalidDetails), /workspace/);
  const runtimeKey = await altered(bytes, (files) => {
    const raw: unknown = JSON.parse(new TextDecoder().decode(files.get("workspace.json")));
    assert.ok(typeof raw === "object" && raw !== null && "editor" in raw &&
      typeof raw.editor === "object" && raw.editor !== null);
    Object.assign(raw.editor, { sessionToken: "do-not-restore" });
    files.set("workspace.json", encoder.encode(JSON.stringify(raw)));
  });
  await assert.rejects(openProject(runtimeKey), /workspace/);
});

test("ZIP traversal, case aliases, symlinks, expansion and unknown version fail", async () => {
  const bytes = await saveProject(base());
  await assert.rejects(openProject(zipSync({ "manifest.json": encoder.encode("{}"), "../evil": original })), /ZIP/);
  await assert.rejects(openProject(zipSync({ "manifest.json": encoder.encode("{}"), "/absolute": original })), /ZIP/);
  await assert.rejects(openProject(zipSync({ "manifest.json": encoder.encode("{}"), "A": original, "a": original })), /ZIP/);
  const link = Uint8Array.from(bytes);
  const view = new DataView(link.buffer, link.byteOffset, link.byteLength);
  const central = view.getUint32(link.length - 22 + 16, true);
  view.setUint32(central + 38, 0xa0000000, true);
  await assert.rejects(openProject(link), /ZIP/);
  const bomb = zipSync({ "manifest.json": encoder.encode("{}"), "huge": new Uint8Array(1024 * 1024) });
  await assert.rejects(openProject(bomb), /ZIP/);
  const unknown = await altered(bytes, (files) => {
    const raw: unknown = JSON.parse(new TextDecoder().decode(files.get("manifest.json")));
    assert.ok(typeof raw === "object" && raw !== null);
    Object.assign(raw, { schemaVersion: 9 });
    files.set("manifest.json", encoder.encode(JSON.stringify(raw)));
  }, false);
  await assert.rejects(openProject(unknown), /version/);
});

test("lying ZIP size aborts streamed inflate before the declared output is exceeded", () => {
  const compressed = zipSync({ "manifest.json": encoder.encode("{}"),
    "source.bin": new Uint8Array(16 * 1024 * 1024) });
  const lie = Uint8Array.from(compressed);
  const view = new DataView(lie.buffer, lie.byteOffset, lie.byteLength);
  const central = view.getUint32(lie.length - 22 + 16, true);
  let local = 0;
  let directory = central;
  for (let index = 0; index < 2; index += 1) {
    const nameLength = view.getUint16(directory + 28, true);
    const compressedSize = view.getUint32(directory + 20, true);
    if (index === 1) {
      view.setUint32(directory + 24, 1024, true);
      view.setUint32(local + 22, 1024, true);
    }
    local += 30 + nameLength + compressedSize;
    directory += 46 + nameLength;
  }
  assert.throws(() => readZip(lie), /within its declared size/);
});

test("forged historical render bytes are never restored as current PDF or DOCX", async () => {
  const saved = await saveProject(base());
  const forged = await altered(saved, (files) => {
    const project = parsed(files.get("project.json"));
    const workspace = parsed(files.get("workspace.json"));
    const manifest = parsed(files.get("manifest.json"));
    assert.ok(typeof project.revision === "number" && record(workspace.editor) &&
      record(workspace.editor.presentation) && typeof workspace.editor.presentation.name === "string" &&
      typeof workspace.editor.presentation.title === "string" && Array.isArray(manifest.entries));
    const presentation = workspace.editor.presentation;
    if (typeof presentation.name !== "string" || typeof presentation.title !== "string")
      throw new Error("missing presentation");
    const entries: unknown[] = manifest.entries as unknown[];
    const request = structuredClone(renderFixture);
    request.baseRevision = project.revision;
    request.snapshot.projectRevision = project.revision;
    request.document.candidate.name = presentation.name;
    request.document.candidate.title = presentation.title;
    request.document.candidate.summary = "FORGED OLD SUMMARY";
    const { snapshotSha256: _oldHash, ...snapshot } = request.snapshot;
    request.snapshot.snapshotSha256 = hash(encoder.encode(JSON.stringify(ordered({
      baseRevision: request.baseRevision, document: request.document, snapshot,
    }))));
    workspace.renderBinding = hash(encoder.encode(JSON.stringify({ project, presentation })));
    for (const [path, data] of [
      ["renders/preview.pdf", encoder.encode("%PDF-FAKE OLD PDF")],
      ["renders/resume.docx", encoder.encode("PKFAKE OLD DOCX")],
      ["renders/request.json", encoder.encode(JSON.stringify(request))],
    ] as const) {
      files.set(path, data);
      entries.push({ path, role: "render", sha256: hash(data), uncompressedSize: data.length });
    }
    files.set("workspace.json", encoder.encode(JSON.stringify(workspace)));
    files.set("manifest.json", encoder.encode(JSON.stringify(manifest)));
  });
  const opened = await openProject(forged);
  assert.equal(opened.render, null);
  assert.match(opened.migration ?? "", /новой локальной сборки/);
  const resaved = readZip(await saveProject({ ...base(), editor: opened.editor }));
  assert.equal(resaved.has("renders/preview.pdf"), false);
  assert.equal(resaved.has("renders/resume.docx"), false);
});

test("highly compressible user text still saves and reopens", async () => {
  const input = base();
  input.editor = { ...initialEditorState, sourceText: "A".repeat(1_000_000), dirty: true };
  const opened = await openProject(await saveProject(input));
  assert.equal(opened.editor.sourceText.length, 1_000_000);
});

test("version 2 selected view keeps exact old text and renders as an editable project", async () => {
  const originalBytes = encoder.encode("Alex Example\nEngineer\nBuilt a service at Example Works in 2021.\n");
  const source = { file: "original.txt", sha256: hash(originalBytes),
    pages: [{ page: 1, text: new TextDecoder().decode(originalBytes) }], warnings: [] };
  const units = [
    { id: "u0001", page: 1, text: "Alex Example" },
    { id: "u0002", page: 1, text: "Engineer" },
    { id: "u0003", page: 1, text: "Built a service at Example Works in 2021." },
  ];
  const s = (text: string, id: string) => ({ text, sources: [id] });
  const archive = { schema_version: 2, as_of: "2026-10-11", source_snapshot: "original.txt", source,
    units, classifications: {
      u0001: { category: "identity", importance: "essential", job_id: null },
      u0002: { category: "role", importance: "essential", job_id: null },
      u0003: { category: "task", importance: "essential", job_id: "job_1" },
    }, jobs: [{ id: "job_1", company: s("Example Works", "u0003"), role: s("Engineer", "u0002"),
      period: s("2021", "u0003"), start: "2021", end: "2022", technologies: [] }],
    global_technologies: [] };
  const archiveBytes = encoder.encode(JSON.stringify(archive));
  const view = { schema_version: 2, archive_sha256: hash(archiveBytes), template: "generic-v1",
    candidate: { name: s("Alex Example", "u0001"), title: s("Engineer", "u0002"),
      summary: s("Built a service at Example Works in 2021.", "u0003") },
    projects: [{ id: "job_1", description: s("Built a service at Example Works in 2021.", "u0003"),
      tasks: [], results: [] }], earlier_experience: [], focus: [], sidebar: [], skill_groups: [],
    coverage: { u0001: { decision: "shown" }, u0002: { decision: "shown" },
      u0003: { decision: "shown" } } };
  const old = writeZip(new Map([
    ["archive.json", archiveBytes], ["source.json", encoder.encode(JSON.stringify(source))],
    ["original.txt", originalBytes], ["view.json", encoder.encode(JSON.stringify(view))],
  ]));
  const opened = await openProject(old);
  assert.equal(opened.editor.presentation?.sourceLanguage, "mixed");
  assert.equal(opened.editor.project?.views.find((block) => block.id === "legacy_prose_job_1")?.state.text,
    "Built a service at Example Works in 2021.");
  assert.deepEqual(opened.projectOriginals[opened.editor.project!.sources[0]!.id], originalBytes);
  const saved = await saveProject({ ...base(), editor: opened.editor, projectOriginals: opened.projectOriginals,
    legacy: opened.legacy });
  const reopened = await openProject(saved);
  assert.deepEqual(reopened.editor.project, opened.editor.project);
  assert.deepEqual(reopened.legacy?.view, view);
});

test("version 3 keeps its exact Project and original while presentation stays unresolved", async () => {
  const project = syntheticProject();
  const projectBytes = encoder.encode(JSON.stringify(project));
  const source = project.sources[0]!;
  const manifest = { schemaVersion: 3, appVersion: "0.1", rendererVersion: "spike-1",
    projectId: project.projectId, entries: [
      { path: "project.json", role: "project", sha256: hash(projectBytes), uncompressedSize: projectBytes.length },
      { path: source.byteRef, role: "source_original", sha256: hash(syntheticSourceBytes),
        uncompressedSize: syntheticSourceBytes.length },
    ] };
  const files = new Map<string, Uint8Array>([["manifest.json", encoder.encode(JSON.stringify(manifest))],
    ["project.json", projectBytes], [source.byteRef, syntheticSourceBytes]]);
  const opened = await openProject(writeZip(files));
  assert.deepEqual(opened.editor.project, project);
  assert.equal(opened.editor.presentation, null);
  assert.deepEqual(opened.projectOriginals[source.id], syntheticSourceBytes);
  assert.match(opened.migration ?? "", /v3/);
  const missing = new Map(files);
  missing.delete(source.byteRef);
  await assert.rejects(openProject(writeZip(missing)), /manifest|original/i);
});

test("unfinished version 2 archive keeps its original and stays saveable before an editor exists", async () => {
  const originalBytes = encoder.encode("Unfinished synthetic source");
  const source = { file: "candidate.txt", sha256: hash(originalBytes),
    pages: [{ page: 1, text: "Unfinished synthetic source" }], warnings: [] };
  const archive = { schema_version: 2, as_of: "2026-10-11", source_snapshot: "original.txt", source,
    units: [{ id: "u0001", page: 1, text: "Unfinished synthetic source" }],
    classifications: {}, jobs: [], global_technologies: [] };
  const files = new Map<string, Uint8Array>([["archive.json", encoder.encode(JSON.stringify(archive))],
    ["source.json", encoder.encode(JSON.stringify(source))], ["original.txt", originalBytes]]);
  const opened = await openProject(writeZip(files));
  assert.equal(opened.editor.project, null);
  assert.deepEqual(opened.legacy?.originalBytes, originalBytes);
  const reopened = await openProject(await saveProject({ ...base(), editor: opened.editor, legacy: opened.legacy }));
  assert.equal(reopened.editor.project, null);
  assert.deepEqual(reopened.legacy?.archive, archive);
  const swapped = await altered(await saveProject({ ...base(), editor: opened.editor, legacy: opened.legacy }), (items) => {
    const replacement = encoder.encode("Different synthetic source");
    const workspace = parsed(items.get("workspace.json"));
    assert.ok(record(workspace.legacy));
    workspace.legacy.originalSha256 = hash(replacement);
    items.set("workspace.json", encoder.encode(JSON.stringify(workspace)));
    items.set("legacy/v2/original", replacement);
  });
  await assert.rejects(openProject(swapped), /workspace|Legacy original/);
  await assert.rejects(saveProject({ ...base(), editor: opened.editor,
    legacy: { ...opened.legacy!, originalBytes: encoder.encode("Different synthetic source") } }), /Legacy original/);
});
