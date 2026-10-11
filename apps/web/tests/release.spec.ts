import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { performance } from "node:perf_hooks";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { unzipSync } from "fflate";
import { acknowledgeVisibleWarnings } from "./export-review";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;
let runRoot: string;

test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-release-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: web, stdio: "pipe" });
});

test.beforeEach(async () => {
  runRoot = mkdtempSync(resolve(temp, "run-"));
  server = spawn(resolve(root, ".venv/bin/python"),
    ["tests/service/browser_release_fixture.py", runRoot, resolve(temp, "dist")], { cwd: root, stdio: "pipe" });
  origin = await new Promise<string>((resolveOrigin, reject) => {
    let output = "";
    let errors = "";
    const timeout = setTimeout(() => reject(new Error("release fixture timed out")), 10_000);
    server.stderr.on("data", (chunk: Buffer) => { errors += chunk.toString("utf8"); });
    server.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const line = output.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timeout); resolveOrigin(line); }
    });
    server.on("exit", () => { clearTimeout(timeout); reject(new Error(`release fixture stopped: ${errors}`)); });
  });
});

test.afterEach(async () => {
  if (server && server.exitCode === null && server.signalCode === null) {
    const stopped = new Promise<void>((resolveStopped) => server.once("exit", () => resolveStopped()));
    server.kill("SIGTERM");
    await stopped;
  }
  expect(existsSync(resolve(runRoot, "generation-attempt"))).toBe(false);
  expect(readdirSync(resolve(runRoot, "operations"))).toEqual([]);
});

test.afterAll(() => { if (temp) rmSync(temp, { recursive: true, force: true }); });

test("continuous synthetic import through rewrite, both exports and reopen", async ({ page }) => {
  test.setTimeout(90_000);
  const calls = { normalize: 0, draft: 0, rewrite: 0, render: 0 };
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path === "/v1/facts/normalize") calls.normalize += 1;
    if (path === "/v1/facts/draft") calls.draft += 1;
    if (path === "/v1/facts/rewrite") calls.rewrite += 1;
    if (path === "/v1/render") calls.render += 1;
  });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Built a local service.\nExample Works Developer 2022-2025");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("button", { name: "Составить черновик" })).toBeVisible();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByLabel("Дата наблюдения, YYYY-MM-DD").fill("2026-10-11");
  await page.getByRole("combobox", { name: "Язык", exact: true }).selectOption("en");
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  expect(calls.normalize).toBe(1);
  expect(calls.draft).toBe(1);
  await page.getByRole("button", { name: "Проект: Example Works", exact: false }).click();
  await page.getByLabel("Текст блока").fill("Example Works delivered a local service.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "О себе", exact: false }).click();
  await page.getByLabel("Уточнение для предложения").fill("Make the profile concise.");
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  await expect(page.getByRole("button", { name: "Применить предложение" })).toBeVisible();
  await page.getByRole("button", { name: "Применить предложение" }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Rewritten: Drafted: Built a local service.");
  expect(calls.rewrite).toBe(1);
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const pdfEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const pdfPath = await (await pdfEvent).path();
  expect(pdfPath).not.toBeNull();
  expect(readFileSync(pdfPath!).subarray(0, 4).toString()).toBe("%PDF");
  const docxEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docxPath = await (await docxEvent).path();
  expect(docxPath).not.toBeNull();
  const document = unzipSync(new Uint8Array(readFileSync(docxPath!)));
  expect(new TextDecoder().decode(document["word/document.xml"])).toContain("Rewritten: Drafted: Built a local service.");
  const projectEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const projectPath = await (await projectEvent).path();
  expect(projectPath).not.toBeNull();
  const projectBytes = readFileSync(projectPath!);
  expect(unzipSync(new Uint8Array(projectBytes))["workspace.json"]).toBeDefined();
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "saved.cvproject",
    mimeType: "application/zip", buffer: projectBytes });
  await page.getByRole("button", { name: "Заменить проект" }).click();
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Rewritten: Drafted: Built a local service.");
  expect(calls).toMatchObject({ normalize: 1, draft: 1, rewrite: 1, render: 1 });
  const field = page.getByLabel("Текст блока");
  await field.focus();
  await page.keyboard.press("End");
  const editSamplesMs: number[] = [];
  for (let index = 0; index < 20; index += 1) {
    const start = performance.now();
    await page.keyboard.type("x");
    editSamplesMs.push(performance.now() - start);
  }
  await expect(field).toHaveValue(/x{20}/);
  const ordered = [...editSamplesMs].sort((left, right) => left - right);
  console.log(`browser edit key dispatch: ${JSON.stringify({ samples: editSamplesMs.length,
    medianMs: ordered[Math.floor(ordered.length / 2)], p95Ms: ordered[Math.ceil(ordered.length * 0.95) - 1] })}`);
  expect(calls).toMatchObject({ normalize: 1, draft: 1, rewrite: 1, render: 1 });
});
