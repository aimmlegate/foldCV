import { expect, test, type Page } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { unzipSync } from "fflate";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;
let runRoot: string;

test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-rewrite-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: web, stdio: "pipe" });
});

test.beforeEach(async () => {
  runRoot = resolve(temp, "run");
  mkdirSync(runRoot);
  server = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_rewrite_fixture.py", runRoot, resolve(temp, "dist")],
    { cwd: root, stdio: "pipe" });
  origin = await new Promise<string>((resolveOrigin, reject) => {
    let output = "";
    let errors = "";
    const timeout = setTimeout(() => reject(new Error("rewrite fixture timed out")), 10_000);
    server.stderr.on("data", (chunk: Buffer) => { errors += chunk.toString("utf8"); });
    server.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const line = output.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timeout); resolveOrigin(line); }
    });
    server.on("exit", () => { clearTimeout(timeout); reject(new Error(`rewrite fixture stopped: ${errors}`)); });
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

test.afterAll(() => { if (temp) rmSync(temp, { recursive: true, force: true }); });

async function openManualProject(page: Page, jobDescription = "Built a local service."): Promise<void> {
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Built a local service.");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Built reliable systems.");
  await page.getByRole("button", { name: "Добавить факт", exact: true }).click();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByLabel("Дата наблюдения, YYYY-MM-DD").fill("2026-10-11");
  await page.getByRole("combobox", { name: "Язык", exact: true }).selectOption("en");
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Example Works");
  await page.getByLabel("Роль").fill("Developer");
  await page.getByLabel("Начало, YYYY или YYYY-MM").fill("2022");
  await page.getByLabel("Конец, пусто если текущая").fill("2025");
  await page.getByLabel("Дословный текст работы").fill(jobDescription);
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
}

test("imported project shows before/after, applies one rewrite, undoes, and renders without another call", async ({ page }) => {
  let rewrites = 0;
  page.on("request", (request) => { if (request.url().endsWith("/v1/facts/rewrite")) rewrites += 1; });
  await openManualProject(page);
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  await page.getByLabel("Уточнение для предложения").fill("Make it concise.");
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  await expect(page.getByText("Rewritten: Built reliable systems.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  expect(rewrites).toBe(1);
  expect(readFileSync(resolve(runRoot, "rewrite-calls"), "utf8")).toBe("1");
  const prompt = JSON.parse(readFileSync(resolve(runRoot, "rewrite-payload.json"), "utf8")) as Record<string, unknown>;
  expect(prompt.task).toBe("rewrite_prose");
  expect(prompt.blockId).toBe("profile");
  expect(JSON.stringify(prompt)).not.toContain("originalBytes");
  await page.getByRole("button", { name: "Применить предложение" }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Rewritten: Built reliable systems.");
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const pdfPath = await (await pdfDownload).path();
  expect(pdfPath).not.toBeNull();
  expect(readFileSync(pdfPath!).subarray(0, 4).toString()).toBe("%PDF");
  const docxDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docxPath = await (await docxDownload).path();
  expect(docxPath).not.toBeNull();
  const documentXml = unzipSync(new Uint8Array(readFileSync(docxPath!)))["word/document.xml"];
  expect(documentXml).toBeDefined();
  const xml = new TextDecoder().decode(documentXml);
  expect(xml).toContain("Built reliable systems.");
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  await expect(page.getByRole("button", { name: "Отклонить предложение" })).toBeVisible();
  await page.getByRole("button", { name: "Отклонить предложение" }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  expect(rewrites).toBe(2);
  expect(readFileSync(resolve(runRoot, "rewrite-calls"), "utf8")).toBe("2");
});

test("fact correction after rewrite, manual lock and undo can reconcile unchanged prose", async ({ page }) => {
  let rewrites = 0;
  page.on("request", (request) => { if (request.url().endsWith("/v1/facts/rewrite")) rewrites += 1; });
  await openManualProject(page);
  const text = page.getByLabel("Текст блока");
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  await expect(page.getByRole("button", { name: "Применить предложение" })).toBeVisible();
  await page.getByRole("button", { name: "Применить предложение" }).click();
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await text.fill("My own profile wording.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await expect(page.getByText("Правка закреплена")).toBeVisible();
  await text.fill("Typing I will cancel.");
  await page.getByRole("button", { name: "Отменить ввод", exact: true }).click();
  await expect(text).toHaveValue("My own profile wording.");
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await expect(text).toHaveValue("Built reliable systems.");
  await page.getByLabel("Значение факта").fill("Built reliable systems and tests.");
  await page.getByRole("button", { name: "Применить факт" }).click();
  await expect(page.getByRole("button", { name: "Проверил факты, оставить текст" })).toBeVisible();
  await page.getByRole("button", { name: "Проверил факты, оставить текст" }).click();
  await expect(page.getByRole("button", { name: "Проверил факты, оставить текст" })).toHaveCount(0);
  await expect(text).toHaveValue("Built reliable systems.");
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await expect(page.getByRole("button", { name: "Проверил факты, оставить текст" })).toBeVisible();
  expect(rewrites).toBe(1);
});

test("all-private rewrite links a safe fact issue, then correction allows retry", async ({ page }) => {
  let requests = 0;
  page.on("request", (request) => { if (request.url().endsWith("/v1/facts/rewrite")) requests += 1; });
  await openManualProject(page, "Call 555-123-4567 about the service.");
  await page.getByRole("button", { name: "Проект: Example Works" }).click();
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  const issue = page.getByRole("alert").filter({ hasText: "fact_user_manual_job_" });
  await expect(issue).toContainText(/prose_job_user_(.+) · fact_user_manual_job_job_user_\1:/);
  await expect(issue).not.toContainText("555-123-4567");
  expect(existsSync(resolve(runRoot, "rewrite-calls"))).toBe(false);
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "fact_user_manual_job_job_user_" })).toBeVisible();
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByLabel("Значение факта").fill("Built a local service.");
  await page.getByRole("button", { name: "Применить факт" }).click();
  await expect(issue).toHaveCount(0);
  await page.getByLabel("Текст блока").fill("Built a local service.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Снять закрепление" }).click();
  await page.getByRole("button", { name: "Предложить новую формулировку" }).click();
  await expect(page.getByText("Rewritten: Built a local service.", { exact: true })).toBeVisible();
  expect(readFileSync(resolve(runRoot, "rewrite-calls"), "utf8")).toBe("1");
  expect(requests).toBe(2);
});
