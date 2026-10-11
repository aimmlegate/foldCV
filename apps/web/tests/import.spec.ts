import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { Route } from "@playwright/test";
import { unzipSync } from "fflate";

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

test("imported source opens a verbatim editor and real PDF and DOCX without generation", async ({ page }) => {
  test.setTimeout(90_000);
  let contentCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite|facts\/normalize|facts\/draft)$/.test(request.url())) contentCalls += 1; });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Synthetic engineer. Skills: Python. Built a local service.");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("heading", { name: "Лист фактов" })).toBeVisible();
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Built reliable systems.");
  await page.getByRole("button", { name: "Добавить факт", exact: true }).click();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByLabel("Дата наблюдения, YYYY-MM-DD").fill("2026-10-11");
  await page.getByRole("combobox", { name: "Язык", exact: true }).selectOption("en");
  await page.getByLabel("Языки, через запятую").fill("English");
  await page.getByLabel("Другие навыки, через запятую").fill("ObscureDB 2.0");
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Example Works");
  await page.getByLabel("Роль").fill("Developer");
  await page.getByLabel("Начало, YYYY или YYYY-MM").fill("2022-01");
  await page.getByLabel("Конец, пусто если текущая").fill("2025-12");
  await page.getByLabel("Дословный текст работы").fill("Built a local service for synthetic records.");
  await page.getByRole("button", { name: "Добавить подпроект" }).click();
  await page.getByLabel("Подпроект").fill("Local client");
  await page.getByLabel("Начало", { exact: true }).fill("2023");
  await page.getByLabel("Конец", { exact: true }).fill("2024");
  await page.getByLabel("Дословный текст", { exact: true }).fill("Prepared local files.");
  await page.getByRole("button", { name: "Добавить число" }).click();
  await page.getByRole("combobox", { name: "Работа", exact: true }).selectOption({ label: "Example Works" });
  await page.getByLabel("Число").fill("20");
  await page.getByLabel("Сравнение").selectOption("at_most");
  await page.getByLabel("Единица").fill("records");
  await page.getByLabel("Чей результат").selectOption("team");
  await page.getByLabel("Период", { exact: true }).fill("day");
  await page.getByLabel("Условия, через запятую").fill("peak");
  await page.getByRole("button", { name: "Добавить руководство" }).click();
  await page.getByRole("combobox", { name: "Работа руководства" }).selectOption({ label: "Example Works" });
  await page.getByLabel("Действие").fill("Built the team");
  await page.getByRole("combobox", { name: "Чей вклад" }).selectOption("personal");
  await page.getByLabel("Размер команды").fill("5");
  await page.getByLabel("Единица команды").fill("engineers");
  await page.getByLabel("Было до изменения").fill("zero");
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Текст блока")).toHaveValue("Built reliable systems.");
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docxPath = await (await download).path();
  expect(docxPath).not.toBeNull();
  const xml = new TextDecoder().decode(unzipSync(new Uint8Array(readFileSync(docxPath!)))["word/document.xml"]);
  expect(xml).toContain("Alex Example");
  expect(xml).toContain("Built reliable systems.");
  expect(xml).toContain("Built a local service for synthetic records.");
  expect(xml).toContain("Prepared local files.");
  expect(xml).toContain("team: at most 20 records per day");
  expect(xml).toContain("personal: Built the team; team size 5 engineers from zero");
  expect(xml).toContain("ObscureDB 2.0");
  expect(xml).toContain("English");
  expect(contentCalls).toBe(0);
  await page.getByRole("button", { name: "1. Загрузка" }).click();
  await page.getByRole("button", { name: "Закрыть проект и перейти к импорту" }).click();
  await expect(page.getByText("Несохранённые правки проекта будут удалены.")).toBeVisible();
  await page.getByRole("button", { name: "Оставить проект" }).click();
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByText("Дословный черновик из импорта", { exact: false })).toBeVisible();
});

test("manual work and subproject without dates stay editable with visible checks", async ({ page }) => {
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Local profile text.");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Undated Works");
  await page.getByLabel("Роль").fill("Developer");
  await page.getByLabel("Дословный текст работы").fill("Built local tools.");
  await page.getByRole("button", { name: "Добавить подпроект" }).click();
  await page.getByLabel("Подпроект").fill("Undated project");
  await page.getByLabel("Дословный текст", { exact: true }).fill("Prepared local documents.");
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.getByText("У работы Undated Works не указан период", { exact: false })).toBeVisible();
  await expect(page.getByText("У подпроекта Undated project не указан период", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Проект: Undated Works", exact: false }).click();
  await expect(page.getByLabel("Текст блока")).toContainText("Built local tools.");
});

test("coverage links source, records an exclusion reason and expires an affected warning", async ({ page }) => {
  let contentCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite|facts\/normalize|facts\/draft)$/.test(request.url()))
    contentCalls += 1; });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Unusual detail from the original source.");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await page.getByLabel("Имя кандидата").fill("Alex Example");
  await page.getByLabel("Должность").fill("Engineer");
  await page.getByLabel("Дата наблюдения, YYYY-MM-DD").fill("2026-10-11");
  await page.getByRole("button", { name: "Добавить работу" }).click();
  await page.getByLabel("Организация").fill("Example Works");
  await page.getByLabel("Роль").fill("Developer");
  await page.getByLabel("Начало, YYYY или YYYY-MM").fill("2022");
  await page.getByLabel("Конец, пусто если текущая").fill("2025");
  await page.getByLabel("Дословный текст работы").fill("Built a local service.");
  await page.getByRole("button", { name: "Добавить число" }).click();
  await page.getByRole("combobox", { name: "Работа", exact: true }).selectOption({ label: "Example Works" });
  await page.getByLabel("Число").fill("20");
  await page.getByLabel("Сравнение").selectOption("at_most");
  await page.getByLabel("Единица").fill("records");
  await page.getByLabel("Чей результат").selectOption("team");
  await page.getByRole("button", { name: "Открыть дословный черновик" }).click();
  await page.getByRole("tab", { name: "Проверки" }).click();
  const metric = page.locator("li").filter({ hasText: "Проверьте число, диапазон" }).first();
  await expect(metric).toBeVisible();
  await page.getByText("Факты ·", { exact: false }).click();
  await expect(page.getByText("Факт: не более 20 records · вклад: командный", { exact: false }).last()).toBeVisible();
  await metric.getByRole("button", { name: "Подтвердить проверку" }).click();
  await expect(metric.getByRole("button", { name: "Снять подтверждение" })).toBeVisible();
  await page.getByText("Фрагменты исходника ·", { exact: false }).click();
  const unit = page.locator("li").filter({ hasText: "Фрагмент" }).filter({ hasText: "Не решён" }).first();
  await unit.getByLabel("Причина исключения").fill("Out of scope for this client");
  await unit.getByRole("button", { name: "Исключить" }).click();
  const excluded = page.locator("li").filter({ hasText: "Причина: Out of scope for this client" });
  await expect(excluded).toBeVisible();
  await excluded.getByRole("button", { name: "Исходник" }).click();
  await expect(page.locator("[id^=source-]").filter({ hasText: "Unusual detail from the original source." })).toBeVisible();
  await page.getByRole("button", { name: "Проект: Example Works", exact: false }).click();
  await page.getByLabel("Текст блока").fill("Built a changed local service.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.locator("li").filter({ hasText: "Проверьте число, диапазон" }).first()
    .getByRole("button", { name: "Подтвердить проверку" })).toBeVisible();
  await page.getByText("Факты ·", { exact: false }).click();
  const proseFact = page.locator("#coverage-facts li").filter({ hasText: "Факт: Built a local service." });
  await expect(proseFact.getByText("Не решён")).toBeVisible();
  await proseFact.getByLabel("Причина исключения или проверки").fill("Reviewed equivalent wording");
  await proseFact.getByRole("button", { name: "Подтвердить изложение" }).click();
  await expect(proseFact.getByText("Показан")).toBeVisible();
  expect(contentCalls).toBe(0);
});

test("imported facts, unresolved dates and user assertions stay available without generation", async ({ page }) => {
  test.setTimeout(60_000);
  let contentCalls = 0;
  let factCalls = 0;
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite|facts\/normalize)$/.test(request.url())) contentCalls += 1; });
  page.on("request", (request) => { if (/\/v1\/facts$/.test(request.url())) factCalls += 1; });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Skills: Python, Docker\nAcme Engineer 2020-2022\nBuilt a team from zero to five");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("heading", { name: "Лист фактов" })).toBeVisible();
  expect(factCalls).toBe(0);
  await page.getByRole("button", { name: "Проверить факты" }).click();
  await expect(page.getByText("Python · общий навык")).toBeVisible();
  await expect(page.getByText("Docker · общий навык")).toBeVisible();
  await expect(page.getByText("Дата без связи").first()).toBeVisible();
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Led a five-person team at Acme");
  await page.getByRole("button", { name: "Добавить факт" }).click();
  await expect(page.getByText("Led a five-person team at Acme")).toBeVisible();
  await expect(page.getByText("Внесено пользователем")).toBeVisible();
  await page.getByLabel("Ваше исправление фрагмента").first().fill("Skills: Kubernetes");
  expect(factCalls).toBe(1);
  await page.getByRole("button", { name: "Обновить факты" }).click();
  await expect(page.getByText("Kubernetes · проверьте контекст")).toBeVisible();
  await expect(page.getByText("Led a five-person team at Acme")).toBeVisible();
  expect(factCalls).toBe(2);
  expect(contentCalls).toBe(0);
});

test("title-only and education-only form drafts keep the replacement boundary", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByLabel("Или вставьте текст резюме").fill("Synthetic text for a partial form.");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  await expect(page.getByRole("heading", { name: "Лист фактов" })).toBeVisible();
  await page.getByLabel("Должность").fill("Pending title only");
  await page.getByLabel("Образование").fill("Pending school only");
  await page.getByLabel("Добавить подтверждённый вами факт").fill("Pending assertion text");
  await page.getByRole("button", { name: "Очистить импорт" }).click();
  await page.getByRole("button", { name: "Подтвердить очистку" }).click();
  await page.getByLabel("Или вставьте текст резюме").fill("");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сохранить проект" }).click();
  const path = await (await download).path();
  expect(path).not.toBeNull();
  const bytes = readFileSync(path!);
  const entries = unzipSync(new Uint8Array(bytes));
  expect(JSON.parse(new TextDecoder().decode(entries["manifest.json"]))).toMatchObject({ projectId: null });
  expect(JSON.parse(new TextDecoder().decode(entries["workspace.json"]))).toMatchObject({
    manualForm: { title: "Pending title only", education: "Pending school only" },
    assertionDraft: "Pending assertion text",
  });
  await page.getByLabel("Открыть .cvproject").setInputFiles({ name: "partial.cvproject",
    mimeType: "application/zip", buffer: bytes });
  await expect(page.getByRole("dialog", { name: "Заменить текущий проект" })).toBeVisible();
  await page.getByRole("button", { name: "Оставить текущий" }).click();
  await page.getByLabel("Или вставьте текст резюме").fill("New local text");
  await expect(page.getByLabel("Или вставьте текст резюме")).toHaveValue("New local text");
});

test("source correction rejects a late earlier fact response", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  let held: Route | null = null;
  let heldBody: Buffer | null = null;
  let factCalls = 0;
  await page.route("**/v1/facts", async (route) => {
    factCalls += 1;
    if (held === null) {
      const response = await route.fetch();
      held = route;
      heldBody = await response.body();
      return;
    }
    await route.continue();
  });
  await page.getByLabel("Или вставьте текст резюме").fill("Skills: Python\n");
  await page.getByRole("button", { name: "Извлечь вставленный текст" }).click();
  expect(factCalls).toBe(0);
  await page.getByRole("button", { name: "Проверить факты" }).click();
  await expect.poll(() => held !== null).toBe(true);
  await page.getByLabel("Ваше исправление фрагмента").first().fill("Skills: Kubernetes");
  expect(factCalls).toBe(1);
  await page.getByRole("button", { name: "Проверить факты" }).click();
  await expect(page.getByText("Kubernetes · проверьте контекст")).toBeVisible();
  expect(factCalls).toBe(2);
  const oldRoute = held as Route | null;
  if (oldRoute && heldBody) {
    try { await oldRoute.fulfill({ status: 200, contentType: "application/json", body: heldBody }); } catch { /* canceled request */ }
  }
  await expect(page.getByText("Python · общий навык")).toHaveCount(0);
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
