import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, existsSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { unzipSync, zipSync } from "fflate";
import { syntheticProject, syntheticSourceBytes } from "../src/editor/example";
import { acknowledgeVisibleWarnings, excludeUnrepresentedFacts } from "./export-review";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;
let runRoot: string;

test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-browser-"));
  const dist = resolve(temp, "dist");
  execFileSync("npm", ["run", "build", "--", "--outDir", dist], { cwd: web, stdio: "pipe" });
});

test.beforeEach(async () => {
  runRoot = mkdtempSync(resolve(temp, "run-"));
  server = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_workflow_fixture.py", runRoot, resolve(temp, "dist")],
    { cwd: root, stdio: "pipe" });
  origin = await new Promise<string>((resolveOrigin, reject) => {
    let output = "";
    let errors = "";
    const timeout = setTimeout(() => reject(new Error("fixture server timed out")), 10_000);
    server.stderr.on("data", (chunk: Buffer) => { errors += chunk.toString("utf8"); });
    server.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const line = output.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timeout); resolveOrigin(line); }
    });
    server.on("exit", () => { clearTimeout(timeout); reject(new Error(`fixture server stopped: ${errors}`)); });
  });
});

test.afterEach(async () => {
  if (server && server.exitCode === null && server.signalCode === null) {
    const stopped = new Promise<void>((resolveStopped) => server.once("exit", () => resolveStopped()));
    server.kill("SIGTERM");
    await stopped;
  }
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
});

test.afterAll(() => { if (temp) rmSync(temp, { recursive: true, force: true }); });

test("real service keeps PDF preview identical to download and DOCX editable with zero generation", async ({ page }) => {
  test.setTimeout(90_000);
  let renders = 0;
  let textCalls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/render")) renders += 1;
    if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1;
  });
  await page.goto(`${origin}/legacy.html#secret=synthetic-browser-secret-0123456789`);
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await page.getByLabel("Текст блока").fill("Synthetic edited profile for exact export.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  const shown = await page.getByTitle("Превью PDF").evaluate(async (iframe) => {
    if (!(iframe instanceof HTMLIFrameElement) || !iframe.src) throw new Error("missing PDF viewer");
    return Array.from(new Uint8Array(await (await fetch(iframe.src)).arrayBuffer()));
  });
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const pdfPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const pdf = await pdfPromise;
  expect(pdf.suggestedFilename()).toBe("resume.pdf");
  const pdfPath = await pdf.path();
  expect(pdfPath).not.toBeNull();
  expect(readFileSync(pdfPath!)).toEqual(Buffer.from(shown));
  const docxPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docx = await docxPromise;
  const docxPath = await docx.path();
  expect(docxPath).not.toBeNull();
  const document = unzipSync(new Uint8Array(readFileSync(docxPath!)));
  expect(new TextDecoder().decode(document["word/document.xml"])).toContain("Synthetic edited profile for exact export.");
  expect(renders).toBe(1);
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByLabel("Текст блока").fill("A second explicit synthetic revision.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const newerDocxPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Собрать и скачать DOCX" }).click();
  const newerDocx = await newerDocxPromise;
  const newerPath = await newerDocx.path();
  expect(newerPath).not.toBeNull();
  const newerDocument = unzipSync(new Uint8Array(readFileSync(newerPath!)));
  expect(new TextDecoder().decode(newerDocument["word/document.xml"])).toContain("A second explicit synthetic revision.");
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("tab", { name: "Превью" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  const newerShown = await page.getByTitle("Превью PDF").evaluate(async (iframe) => {
    if (!(iframe instanceof HTMLIFrameElement) || !iframe.src) throw new Error("missing PDF viewer");
    return Array.from(new Uint8Array(await (await fetch(iframe.src)).arrayBuffer()));
  });
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const newerPdfPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const newerPdfPath = await (await newerPdfPromise).path();
  expect(newerPdfPath).not.toBeNull();
  expect(readFileSync(newerPdfPath!)).toEqual(Buffer.from(newerShown));
  expect(renders).toBe(2);
  expect(textCalls).toBe(0);
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
});

test("saved project reopens with verified template and rebuilds PDF before export", async ({ page }) => {
  test.setTimeout(90_000);
  let externalRequests = 0;
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    externalRequests += 1;
    return route.abort();
  });
  let renders = 0;
  let textCalls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/render")) renders += 1;
    if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1;
  });
  await page.goto(`${origin}/legacy.html#secret=synthetic-browser-secret-0123456789`);
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await page.getByLabel("Текст блока").fill("Saved synthetic profile for reopen.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const savedPath = await (await downloadPromise).path();
  expect(savedPath).not.toBeNull();
  const bytes = readFileSync(savedPath!);
  const entries = unzipSync(new Uint8Array(bytes));
  expect(entries["project.json"]).toBeDefined();
  expect(entries["workspace.json"]).toBeDefined();
  expect(entries["template/manifest.json"]).toBeDefined();
  const template = JSON.parse(new TextDecoder().decode(entries["template/manifest.json"])) as unknown;
  expect(template).toMatchObject({ assets: expect.any(Object) });
  if (typeof template !== "object" || template === null || !("assets" in template) ||
      typeof template.assets !== "object" || template.assets === null) throw new Error("template assets missing");
  for (const [asset, expected] of Object.entries(template.assets)) {
    const data = entries[`template/${asset}`];
    expect(data).toBeDefined();
    expect(createHash("sha256").update(data!).digest("hex")).toBe(expected);
  }
  expect(entries["renders/preview.pdf"]).toBeUndefined();
  expect(entries["renders/resume.docx"]).toBeUndefined();
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "saved.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByRole("dialog", { name: "Заменить текущий проект" })).toBeVisible();
  await page.getByRole("button", { name: "Заменить проект" }).click();
  await expect(page.getByLabel("Текст блока")).toHaveValue("Saved synthetic profile for reopen.");
  await expect(page.getByText("PDF готов", { exact: false })).toHaveCount(0);
  expect(renders).toBe(1);
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  expect(renders).toBe(2);
  const rebuilt = await page.getByTitle("Превью PDF").evaluate(async (iframe) => {
    if (!(iframe instanceof HTMLIFrameElement) || !iframe.src) throw new Error("missing PDF viewer");
    return Array.from(new Uint8Array(await (await fetch(iframe.src)).arrayBuffer()));
  });
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const rebuiltDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const rebuiltPath = await (await rebuiltDownload).path();
  expect(rebuiltPath).not.toBeNull();
  expect(readFileSync(rebuiltPath!)).toEqual(Buffer.from(rebuilt));
  await page.route("**/v1/template-package", (route) => route.fulfill({ status: 503, body: "unavailable" }));
  const secondDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const secondPath = await (await secondDownload).path();
  expect(secondPath).not.toBeNull();
  const secondEntries = unzipSync(new Uint8Array(readFileSync(secondPath!)));
  for (const [path, data] of Object.entries(entries)) {
    if (path.startsWith("template/")) expect(secondEntries[path]).toEqual(data);
  }
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("tab", { name: "Превью" }).click();
  const edited = "Current unsaved project must survive cancel and corruption.";
  await page.getByLabel("Текст блока").fill(edited);
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "saved.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByRole("dialog", { name: "Заменить текущий проект" })).toBeVisible();
  await page.getByRole("button", { name: "Оставить текущий" }).click();
  await expect(page.getByLabel("Текст блока")).toHaveValue(edited);
  const corrupt = Buffer.from(bytes);
  corrupt[100] = (corrupt[100] ?? 0) ^ 0xff;
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "bad.cvproject",
    mimeType: "application/zip", buffer: corrupt });
  await expect(page.getByRole("alert")).toContainText("Архив не открыт");
  await expect(page.getByLabel("Текст блока")).toHaveValue(edited);
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  expect(renders).toBe(3);
  expect(textCalls).toBe(0);
  expect(externalRequests).toBe(0);
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
  await page.reload();
  await page.getByLabel("Или вставьте текст резюме").fill("Unapplied source paste");
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "saved.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByRole("dialog", { name: "Заменить текущий проект" })).toBeVisible();
  await page.getByRole("button", { name: "Оставить текущий" }).click();
  await expect(page.getByLabel("Или вставьте текст резюме")).toHaveValue("Unapplied source paste");
});

test("archive replacement aborts a delayed prepare before the new local render", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(`${origin}/legacy.html#secret=synthetic-browser-secret-0123456789`);
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const savedPath = await (await download).path();
  expect(savedPath).not.toBeNull();
  let prepares = 0;
  let markOldStarted!: () => void;
  const oldStarted = new Promise<void>((resolveStarted) => { markOldStarted = resolveStarted; });
  let releaseOld!: () => void;
  const oldGate = new Promise<void>((resolveOld) => { releaseOld = resolveOld; });
  await page.route("**/v1/prepare-render", async (route) => {
    prepares += 1;
    if (prepares === 1) {
      markOldStarted();
      await oldGate;
      try { await route.continue(); } catch { /* The replacement aborted this request. */ }
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await oldStarted;
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "saved.cvproject",
    mimeType: "application/zip", buffer: readFileSync(savedPath!) });
  await expect(page.getByRole("dialog", { name: "Заменить текущий проект" })).toBeVisible();
  await page.getByRole("button", { name: "Заменить проект" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toHaveCount(0);
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  expect(prepares).toBe(2);
  releaseOld();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
});

test("version 2 selected view renders locally after migration and reopen", async ({ page }) => {
  test.setTimeout(90_000);
  const original = new TextEncoder().encode("Alex Example\nEngineer\nBuilt a service at Example Works in 2021.\nPython and Example School\n");
  const digest = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");
  const statement = (text: string, id: string) => ({ text, sources: [id] });
  const source = { file: "original.txt", sha256: digest(original), warnings: [],
    pages: [{ page: 1, text: new TextDecoder().decode(original) }] };
  const archive = { schema_version: 2, as_of: "2026-10-11", source_snapshot: "original.txt", source,
    units: [{ id: "u0001", page: 1, text: "Alex Example" }, { id: "u0002", page: 1, text: "Engineer" },
      { id: "u0003", page: 1, text: "Built a service at Example Works in 2021." },
      { id: "u0004", page: 1, text: "Python and Example School" }],
    classifications: { u0001: { category: "identity", importance: "essential", job_id: null },
      u0002: { category: "role", importance: "essential", job_id: null },
      u0003: { category: "task", importance: "essential", job_id: "job_1" },
      u0004: { category: "education", importance: "supporting", job_id: null } },
    jobs: [{ id: "job_1", company: statement("Example Works", "u0003"), role: statement("Engineer", "u0002"),
      period: statement("2021", "u0003"), start: "2021", end: "2022", technologies: [] }],
    global_technologies: [] };
  const archiveBytes = new TextEncoder().encode(JSON.stringify(archive));
  const view = { schema_version: 2, archive_sha256: digest(archiveBytes), template: "generic-v1",
    candidate: { name: statement("Alex Example", "u0001"), title: statement("Engineer", "u0002"),
      summary: statement("Built a service at Example Works in 2021.", "u0003") },
    projects: [{ id: "job_1", company: statement("Example Works", "u0003"),
      period: statement("2021", "u0003"), role: statement("Engineer", "u0002"),
      stack: statement("Python", "u0004"),
      description: statement("Built a service at Example Works in 2021.", "u0003"),
      tasks: [], results: [] }], earlier_experience: [],
    focus: [{ label: statement("Python", "u0004"), duration: null }],
    sidebar: [{ title: "ОБРАЗОВАНИЕ", items: [statement("Example School", "u0004")] }],
    skill_groups: [{ title: "ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ", items: statement("Python", "u0004") }],
    achievements: [statement("Built a service at Example Works in 2021.", "u0003")],
    coverage: { u0001: { decision: "shown" }, u0002: { decision: "shown" },
      u0003: { decision: "shown" }, u0004: { decision: "shown" } } };
  const bytes = Buffer.from(zipSync({ "archive.json": archiveBytes,
    "source.json": new TextEncoder().encode(JSON.stringify(source)), "original.txt": original,
    "view.json": new TextEncoder().encode(JSON.stringify(view)) }, { level: 0 }));
  let textCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1; });
  await page.goto(`${origin}/legacy.html#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "legacy.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByLabel("Текст блока")).toHaveValue(/Built a service at Example Works in 2021/);
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  await excludeUnrepresentedFacts(page);
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  await page.getByText("Оставшиеся признанные неоднозначности", { exact: false }).click();
  await expect(page.getByText(/^Имя кандидата: Проверьте, что имя или должность/)).toBeVisible();
  await expect(page.getByText(/^Должность: Проверьте, что имя или должность/)).toBeVisible();
  const docxDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docxPath = await (await docxDownload).path();
  expect(docxPath).not.toBeNull();
  const document = unzipSync(new Uint8Array(readFileSync(docxPath!)));
  const documentText = new TextDecoder().decode(document["word/document.xml"]);
  expect(documentText).toContain("Python");
  expect(documentText).toContain("Example School");
  const save = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const savedPath = await (await save).path();
  expect(savedPath).not.toBeNull();
  await page.reload();
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "migrated.cvproject",
    mimeType: "application/zip", buffer: readFileSync(savedPath!) });
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByLabel("Текст блока")).toHaveValue(/Built a service at Example Works in 2021/);
  await expect(page.getByText("PDF готов", { exact: false })).toHaveCount(0);
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  expect(textCalls).toBe(0);
});

test("version 3 requires explicit presentation fields before local render", async ({ page }) => {
  test.setTimeout(90_000);
  const project = syntheticProject();
  const projectBytes = new TextEncoder().encode(JSON.stringify(project));
  const source = project.sources[0]!;
  const digest = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");
  const manifest = { schemaVersion: 3, appVersion: "0.1", rendererVersion: "spike-1",
    projectId: project.projectId, entries: [
      { path: "project.json", role: "project", sha256: digest(projectBytes), uncompressedSize: projectBytes.length },
      { path: source.byteRef, role: "source_original", sha256: digest(syntheticSourceBytes),
        uncompressedSize: syntheticSourceBytes.length },
    ] };
  const bytes = Buffer.from(zipSync({ "manifest.json": new TextEncoder().encode(JSON.stringify(manifest)),
    "project.json": projectBytes, [source.byteRef]: syntheticSourceBytes }, { level: 0 }));
  let textCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1; });
  await page.goto(`${origin}/legacy.html#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "old-v3.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByRole("heading", { name: "Данные для архива v3" })).toBeVisible();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByRole("heading", { name: "Данные для архива v3" }).locator("..").getByRole("combobox").first().selectOption("en");
  for (const job of project.employment) {
    const blockId = job.id === "job_1" ? "job_1_prose" : "job_2_prose";
    await page.getByLabel(`${job.employer} · ${job.role}`).selectOption(blockId);
  }
  await page.getByRole("button", { name: "Применить данные" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  expect(textCalls).toBe(0);
});
