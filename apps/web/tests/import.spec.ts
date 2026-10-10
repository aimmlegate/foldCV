import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { Route } from "@playwright/test";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
const fixtures = resolve(root, "tests/fixtures/synthetic/import");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;
let runRoot: string;
let runNumber = 0;

test.beforeAll(async () => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-import-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: web, stdio: "pipe" });
});

test.beforeEach(async () => {
  runRoot = resolve(temp, `run-${runNumber++}`);
  mkdirSync(runRoot);
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
  if (server && server.exitCode === null) {
    const stopped = new Promise<void>((resolveStopped) => server.once("exit", () => resolveStopped()));
    server.kill("SIGTERM");
    await stopped;
  }
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
  expect(readdirSync(resolve(runRoot, "operations"))).toEqual([]);
});

test.afterAll(() => {
  if (temp) rmSync(temp, { recursive: true, force: true });
});

test("real service imports PDF, DOCX and paste with visible gaps and exact original bytes", async ({ page }) => {
  test.setTimeout(60_000);
  let textCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1; });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Выберите PDF, DOCX, TXT или Markdown").setInputFiles(resolve(fixtures, "mixed-columns.pdf"));
  await expect(page.getByText("4 стр. · 6 фрагментов · 4 пробелов", { exact: false })).toBeVisible();
  await expect(page.getByText("Текст на этой странице не найден").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Открыть оригинал PDF" })).toHaveAttribute("href", /^blob:/);
  await page.getByLabel("Ваш текст для этого места").first().fill("Текст на изображении добавлен пользователем");
  await expect(page.getByText("Repeated header", { exact: false }).first()).toBeVisible();
  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать исходный файл" }).click();
  const pdf = await pdfDownload;
  expect(readFileSync((await pdf.path())!)).toEqual(readFileSync(resolve(fixtures, "mixed-columns.pdf")));
  await page.getByLabel("Выберите PDF, DOCX, TXT или Markdown").setInputFiles(resolve(fixtures, "rich.docx"));
  await expect(page.getByRole("heading", { name: "rich.docx" })).toBeVisible();
  await expect(page.getByText("Текстовое поле не прочитано")).toBeVisible();
  await expect(page.getByText("Header repeated")).toBeVisible();
  await expect(page.getByText("Footer text")).toBeVisible();
  await page.getByText("Ссылки в исходном DOCX").click();
  await expect(page.getByText("https://example.invalid/profile")).toBeVisible();
  await page.getByLabel("Принятые источники (2)").selectOption({ label: "mixed-columns.pdf" });
  await expect(page.getByLabel("Ваш текст для этого места").first()).toHaveValue("Текст на изображении добавлен пользователем");
  await page.getByLabel("Или вставьте текст резюме").fill("First\r\nПривет");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("heading", { name: "pasted.txt" })).toBeVisible();
  expect(textCalls).toBe(0);
});

test("real service keeps quoted and literal percent filenames distinct from transport metadata", async ({ page }) => {
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  const bytes = readFileSync(resolve(fixtures, "unicode.txt"));
  const input = page.getByLabel("Выберите PDF, DOCX, TXT или Markdown");
  await input.setInputFiles({ name: 'resume "draft".txt', mimeType: "text/plain", buffer: bytes });
  await expect(page.getByRole("heading", { name: 'resume "draft".txt' })).toBeVisible();
  await page.getByLabel("Ваше исправление фрагмента").first().fill("Manual correction");
  await input.setInputFiles({ name: "resume %22draft%22.txt", mimeType: "text/plain", buffer: bytes });
  await expect(page.getByRole("heading", { name: "resume %22draft%22.txt" })).toBeVisible();
  await expect(page.getByLabel("Ваше исправление фрагмента").first()).toHaveValue("Manual correction");
  await expect(page.getByLabel("Принятые источники (1)")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать исходный файл" }).click();
  const original = await download;
  expect(original.suggestedFilename()).toBe("resume %22draft%22.txt");
  expect(readFileSync((await original.path())!)).toEqual(bytes);
});

test("newer file selection ignores a late earlier response and keeps accepted source", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Выберите PDF, DOCX, TXT или Markdown").setInputFiles(resolve(fixtures, "unicode.txt"));
  await expect(page.getByRole("heading", { name: "unicode.txt" })).toBeVisible();
  let held: Route | null = null;
  let heldBody: Buffer | null = null;
  await page.route("**/v1/extract", async (route) => {
    if (held === null) {
      const response = await route.fetch();
      held = route;
      heldBody = await response.body();
      return;
    }
    await route.continue();
  });
  await page.getByLabel("Выберите PDF, DOCX, TXT или Markdown").setInputFiles(resolve(fixtures, "mixed-columns.pdf"));
  await expect.poll(() => held !== null).toBe(true);
  await page.getByLabel("Выберите PDF, DOCX, TXT или Markdown").setInputFiles(resolve(fixtures, "notes.md"));
  await expect(page.getByRole("heading", { name: "notes.md" })).toBeVisible();
  const oldRoute = held as Route | null;
  if (oldRoute && heldBody) {
    try { await oldRoute.fulfill({ status: 200, contentType: "application/json", body: heldBody }); } catch { /* canceled request */ }
  }
  await expect(page.getByLabel("Принятые источники (2)")).toBeVisible();
  await expect(page.getByText("mixed-columns.pdf", { exact: true })).toHaveCount(0);
});
