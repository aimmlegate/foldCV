import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { Page, Route } from "@playwright/test";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;
let runRoot: string;
let runNumber = 0;

test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-draft-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: web, stdio: "pipe" });
});

test.beforeEach(async () => {
  runRoot = resolve(temp, `run-${runNumber++}`);
  mkdirSync(runRoot);
  server = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_draft_fixture.py", runRoot, resolve(temp, "dist")],
    { cwd: root, stdio: "pipe" });
  origin = await new Promise<string>((resolveOrigin, reject) => {
    let output = "";
    let errors = "";
    const timeout = setTimeout(() => reject(new Error("draft fixture timed out")), 10_000);
    server.stderr.on("data", (chunk: Buffer) => { errors += chunk.toString("utf8"); });
    server.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const line = output.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timeout); resolveOrigin(line); }
    });
    server.on("exit", () => { clearTimeout(timeout); reject(new Error(`draft fixture stopped: ${errors}`)); });
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

async function source(page: Page, text =
  "Built a local service.\nExample Works Developer 2022-2025") {
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill(text);
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("button", { name: "Составить черновик" })).toBeVisible();
}

async function identity(page: Page) {
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByLabel("Дата наблюдения, YYYY-MM-DD").fill("2026-10-11");
  await page.getByRole("combobox", { name: "Язык", exact: true }).selectOption("en");
}

test("real import and fixture two-operation draft reach reviewable editor while manual content stays", async ({ page }) => {
  let normalized = 0;
  let drafted = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/facts/normalize")) normalized += 1;
    if (request.url().endsWith("/v1/facts/draft")) drafted += 1;
  });
  await source(page);
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Built reliable systems.");
  await page.getByRole("button", { name: "Добавить факт", exact: true }).click();
  await identity(page);
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Manual Works");
  await page.getByLabel("Роль").fill("Consultant");
  await page.getByLabel("Начало, YYYY или YYYY-MM").fill("2020");
  await page.getByLabel("Конец, пусто если текущая").fill("2021");
  await page.getByLabel("Дословный текст работы").fill("Kept manual work verbatim.");
  await page.getByRole("button", { name: "Добавить число" }).click();
  await page.getByLabel("Число").fill("7");
  await page.getByLabel("Единица").fill("systems");
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  expect(normalized).toBe(1);
  expect(drafted).toBe(1);
  await expect(page.getByText("Завершённых текстовых операций в этой сессии: 2")).toBeVisible();
  await expect(page.getByRole("button", { name: "Проект: Example Works", exact: false })).toContainText("Предложено · требует проверки");
  await page.getByRole("button", { name: "Проект: Example Works", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Drafted: Example Works Developer 2022-2025");
  await page.getByRole("button", { name: "Проект: Manual Works", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Kept manual work verbatim.");
  await page.getByRole("button", { name: "О себе", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("7 systems");
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.getByText("Модельный текст профиля не запрашивался", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
});

test("failed normalization never starts drafting and manual editor remains available", async ({ page }) => {
  let drafts = 0;
  page.on("request", (request) => { if (request.url().endsWith("/v1/facts/draft")) drafts += 1; });
  await source(page, "FAIL_NORMALIZE\nExample Works Developer 2022-2025");
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Не удалось составить черновик.", { exact: false })).toBeVisible();
  expect(drafts).toBe(0);
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
});

test("source profile and explicit user assertion reach the generated profile", async ({ page }) => {
  await source(page);
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Built reliable systems.");
  await page.getByRole("button", { name: "Добавить факт", exact: true }).click();
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Текст блока")).toContainText("Built reliable systems.");
  await expect(page.getByRole("button", { name: "О себе", exact: false })).toContainText("Предложено · требует проверки");
});

test("editor source correction remains a user assertion and keeps source text visible", async ({ page }) => {
  await source(page);
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Проект: Example Works", exact: false }).click();
  const correction = page.getByLabel("Ваше исправление текстом").first();
  await expect(correction).toBeVisible();
  await correction.fill("Built a different local service.");
  await page.getByRole("button", { name: "Применить факт" }).first().click();
  await expect(page.getByText("Built a different local service.", { exact: false })).toBeVisible();
  await expect(page.getByText("внесено пользователем", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Проект: Example Works", exact: false })).toContainText("Нужно проверить");
  await page.getByRole("tab", { name: "Источники" }).click();
  await expect(page.getByRole("tabpanel", { name: "Источники" }).getByText("Example Works Developer 2022-2025", { exact: false }).first()).toBeVisible();
});

test("private metric and mixed fact stay out of draft input and remain visible as review issues", async ({ page }) => {
  await source(page, "PRIVATE_FIELD profile\nExample Works Developer 2022-2025");
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  const guard = JSON.parse(readFileSync(resolve(runRoot, "draft-payload-guard.json"), "utf8")) as {
    containsPrivateText: boolean; containsPrivateIds: boolean };
  expect(guard).toEqual({ containsPrivateText: false, containsPrivateIds: false });
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.locator('button[title="fact_fixture_private_metric"]').first()).toBeVisible();
  await expect(page.locator('button[title="fact_fixture_private_mixed"]').first()).toBeVisible();
  await expect(page.getByText("555-123-4567", { exact: false })).toHaveCount(0);
  const checks = page.getByRole("tabpanel", { name: "Проверки" });
  const issueRows = await checks.locator("section ul li").count();
  const countText = await checks.locator("li").first().innerText();
  const reviewCount = Number(countText.match(/^(\d+) пунктов проверки$/)?.[1]);
  expect(reviewCount).toBeGreaterThanOrEqual(issueRows);
  expect(issueRows).toBeGreaterThan(0);
  await expect(page.getByText(`${reviewCount} пунктов проверки · 0 устаревших блоков`)).toBeVisible();
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  await expect(page.locator("main").getByText(new RegExp(`${reviewCount} пунктов проверки$`))).toBeVisible();
});

test("withheld source job fallback cannot preview until its visible prose is corrected", async ({ page }) => {
  let renders = 0;
  let drafts = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/render")) renders += 1;
    if (request.url().endsWith("/v1/facts/draft")) drafts += 1;
  });
  await source(page, "Built a safe service.\nExample Works Developer 2022-2025. Call 555-123-4567.");
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Черновик из импорта · предложение требует проверки", { exact: false })).toBeVisible();
  expect(drafts).toBe(1);
  await page.getByRole("button", { name: "Проект: Example Works", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("555-123-4567");
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByRole("alert").getByText("В видимом разделе работы есть контакт", { exact: false })).toBeVisible();
  expect(renders).toBe(0);
  expect(drafts).toBe(1);
  await page.getByRole("tab", { name: "Источники" }).click();
  await expect(page.getByRole("tabpanel", { name: "Источники" }).getByText("555-123-4567", { exact: false }).first()).toBeVisible();
  await page.getByLabel("Текст блока").fill("Built a safe service for Example Works.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  expect(renders).toBe(1);
});

test("manual job output blocks export until explicit correction", async ({ page }) => {
  let renders = 0;
  let drafts = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/render")) renders += 1;
    if (request.url().endsWith("/v1/facts/draft")) drafts += 1;
  });
  await source(page, "Built a safe service.");
  await identity(page);
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Manual Works");
  await page.getByLabel("Роль").fill("Engineer");
  await page.getByLabel("Начало, YYYY или YYYY-MM").fill("2022");
  await page.getByLabel("Конец, пусто если текущая").fill("2025");
  await page.getByLabel("Дословный текст работы").fill("Built a tool. Call 555-123-4567.");
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  await page.getByRole("button", { name: "Собрать и скачать DOCX" }).click();
  await expect(page.getByRole("alert").getByText("В видимом разделе работы есть контакт", { exact: false })).toBeVisible();
  expect(renders).toBe(0);
  expect(drafts).toBe(0);
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("button", { name: "Проект: Manual Works", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("555-123-4567");
  await page.getByLabel("Текст блока").fill("Built a safe tool for Manual Works.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Собрать и скачать DOCX" }).click();
  expect((await download).suggestedFilename()).toBe("resume.docx");
  expect(renders).toBe(1);
  expect(drafts).toBe(0);
});

test("all private candidates fail before provider input and leave the manual route available", async ({ page }) => {
  await source(page, "ALL_PRIVATE Call 5551234567\nALL_PRIVATE Call 5551234567");
  await identity(page);
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect(page.getByText("Не удалось составить черновик.", { exact: false })).toBeVisible();
  expect(existsSync(resolve(runRoot, "provider-started"))).toBe(false);
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
});

test("fact and source edits during normalization discard the late result", async ({ page }) => {
  let drafts = 0;
  page.on("request", (request) => { if (request.url().endsWith("/v1/facts/draft")) drafts += 1; });
  await source(page);
  await identity(page);
  let held: Route | null = null;
  let bytes: Buffer | null = null;
  await page.route("**/v1/facts/normalize", async (route) => {
    const response = await route.fetch();
    held = route;
    bytes = await response.body();
  });
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect.poll(() => held !== null).toBe(true);
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Accepted after request.");
  await page.getByRole("button", { name: "Добавить факт", exact: true }).click();
  await page.getByLabel("Ваше исправление фрагмента").first().fill("Updated source wording");
  const oldRoute = held as Route | null;
  if (oldRoute && bytes) {
    try { await oldRoute.fulfill({ status: 200, contentType: "application/x-ndjson", body: bytes }); }
    catch { /* cancelled request */ }
  }
  await expect(page.getByText("Accepted after request.")).toBeVisible();
  await expect(page.getByLabel("Ваше исправление фрагмента").first()).toHaveValue("Updated source wording");
  expect(drafts).toBe(0);
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
});

test("cancel and manual edit discard late generation while accepted import survives", async ({ page }) => {
  await source(page);
  await identity(page);
  let held: Route | null = null;
  let bytes: Buffer | null = null;
  await page.route("**/v1/facts/draft", async (route) => {
    const response = await route.fetch();
    held = route;
    bytes = await response.body();
  });
  await page.getByRole("button", { name: "Составить черновик" }).click();
  await expect.poll(() => held !== null).toBe(true);
  await page.getByRole("button", { name: "Отменить составление" }).click();
  await page.getByLabel("Должность").fill("Senior Engineer");
  const oldRoute = held as Route | null;
  if (oldRoute && bytes) {
    try { await oldRoute.fulfill({ status: 200, contentType: "application/x-ndjson", body: bytes }); }
    catch { /* cancelled request */ }
  }
  await expect(page.getByRole("heading", { name: "Лист фактов" })).toBeVisible();
  await expect(page.getByLabel("Должность")).toHaveValue("Senior Engineer");
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
});
