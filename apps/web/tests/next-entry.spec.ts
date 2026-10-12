import { expect, test } from "@playwright/test";
import { execFileSync, spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdtempSync, readFileSync, realpathSync, rmSync, cpSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import type { GuiProjectResponse } from "../src/contracts/generated/gui_project_response";
import { validateContract } from "../src/contracts/validate";

const root = resolve(import.meta.dirname, "../../..");
let temp: string, runRoot: string, origin: string;
let server: ChildProcessWithoutNullStreams | undefined;
test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-next-entry-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: resolve(root, "apps/web"), stdio: "pipe" });
});
test.beforeEach(async ({}, info) => {
  runRoot = mkdtempSync(resolve(temp, "run-"));
  cpSync(resolve(temp, "dist"), resolve(runRoot, "dist"), { recursive: true });
  const example = info.title.includes("focus warning") ? "E2-focus" : info.title.includes("E2") ? "E2" : "E1";
  const child = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_next_fixture.py", runRoot, resolve(runRoot, "dist"), example], { cwd: root, stdio: "pipe" });
  server = child;
  origin = await new Promise<string>((ready, reject) => {
    let text = "";
    const timer = setTimeout(() => reject(new Error("Controlled entry server timed out")), 15000);
    child.stdout.on("data", (chunk: Buffer) => {
      text += chunk.toString("utf8"); const line = text.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timer); ready(line); }
    });
    child.once("exit", () => { clearTimeout(timer); reject(new Error("Controlled entry server stopped")); });
  });
});
test.afterEach(async () => {
  if (server && server.exitCode === null && server.signalCode === null) {
    const exit = new Promise<void>(ready => server?.once("exit", () => ready()));
    server.kill("SIGTERM"); await exit;
  }
  if (existsSync(resolve(runRoot, "operations"))) expect(readdirSync(resolve(runRoot, "operations"))).toEqual([]);
});
test.afterAll(() => { if (temp) rmSync(temp, { recursive: true, force: true }); });
function response(value: unknown): GuiProjectResponse {
  if (!isResponse(value)) throw new Error("Invalid project response");
  return value;
}
function isResponse(value: unknown): value is GuiProjectResponse { return validateContract("gui_project_response", value); }

test("built API entry creates E1 with two operations and no browser assembly or fact forms", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(1);
  expect(new URL(page.url()).hash).toBe("");
  await expect(page.getByRole("button", { name: "Создать резюме" })).toBeDisabled();
  await page.getByRole("button", { name: "Открыть пример" }).click();
  const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8");
  await expect(page.getByLabel("Или вставьте текст")).toHaveValue(raw);
  const created = page.waitForResponse(result => new URL(result.url()).pathname === "/v1/projects" && result.request().method() === "POST");
  await page.getByRole("button", { name: "Создать резюме" }).click();
  const initial: unknown = await (await created).json();
  const id = response(initial).workspace.projectId;
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Разрабатываю backend-сервисы на Python.");
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
  const value: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  const workspace = response(value).workspace;
  expect(workspace.project?.operations.map(operation => operation.usage?.logicalAttempts)).toEqual([1, 1]);
  expect(workspace.project?.renders).toHaveLength(1);
  expect([workspace.projectRevision, workspace.documentRevision]).toEqual([2, 2]);
  expect(response(value).durability).toBe("in_memory");
  const artifact = workspace.project?.renders[0];
  const link = page.getByRole("link", { name: "Скачать исходный DOCX" });
  await expect(link).toHaveAttribute("href", `/v1/projects/${id}/renders/${artifact?.id}/docx`);
  const downloaded = page.waitForEvent("download");
  await link.click();
  const file = await downloaded;
  const path = await file.path();
  expect(path).not.toBeNull();
  const bytes = readFileSync(path ?? "");
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(artifact?.docx?.sha256);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  await expect(page.getByRole("button", { name: "Сохранить проект", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Экспорт DOCX", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Настройки", exact: true })).toBeVisible();
});

test("built E2 entry locates empty sections and one shared conflict outside editable text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-annotation-type="missing"]')).toHaveCount(3);
  await expect(page.locator('[data-section-id="education"]')).toHaveText("Образование не указано");
  await expect(page.locator('[data-section-id="languages"]')).toHaveText("Языки не указаны");
  const conflict = page.locator('[data-annotation-code="team_size_conflict"]');
  await expect(conflict).toHaveCount(1);
  await expect(conflict).toHaveAttribute("contenteditable", "false");
  const anchor = await conflict.getAttribute("data-anchor-field");
  expect(anchor).toMatch(/^job:.+\/context$/);
  await expect(page.locator(`[data-field-content="${anchor}"]`)).toHaveText("");
  await expect(page.locator('[data-annotation-code="missing_surname"]')).toHaveCount(0);
  await expect(page.locator('[data-field-content^="education:"]')).toHaveCount(0);
  await expect(page.locator('[data-field-content^="language:"]')).toHaveCount(0);
  expect(await page.locator('[data-field-content]').allTextContents()).not.toContain("Образование не указано");
  await expect(page.getByRole("link", { name: "Скачать исходный DOCX" })).toBeVisible();
});

test("built E2 focus warning stays at skills and outside authored text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const warning = page.locator('[data-annotation-code="focus_entry_removed"]');
  await expect(warning).toHaveAttribute("data-annotation-type", "warning");
  await expect(warning).toHaveAttribute("data-section-id", "skills-focus");
  await expect(warning).toHaveAttribute("contenteditable", "false");
  await expect(page.locator('[data-annotation-type="missing"]')).toHaveCount(3);
  expect((await page.locator('[data-field-content]').allTextContents()).join(" ")).not.toContain("исключена из фокуса");
});

test("built E1 source panel reads captured job evidence with zero extra content operations", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const context = page.locator('[data-field-content$="/context"]').first();
  await context.evaluate(field => {
    const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    const root = document.querySelector<HTMLElement>('[contenteditable="true"]');
    if (!text || !root) throw new Error("Context field is missing");
    root.focus(); window.getSelection()?.setBaseAndExtent(text, 0, text, text.textContent?.length ?? 0);
    document.dispatchEvent(new Event("selectionchange"));
  });
  const read = page.waitForResponse(result => new URL(result.url()).pathname.endsWith("/source-context"));
  await page.getByRole("button", { name: "Показать исходник" }).click();
  const result: unknown = await (await read).json();
  expect(validateContract("source_context", result)).toBe(true);
  const panel = page.getByRole("complementary", { name: "Исходный контекст" });
  await expect(panel.locator("blockquote", { hasText: "Сервис обработки заказов." }).first()).toBeVisible();
  await expect(panel.locator('[data-source-relation="exact"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Закрыть исходный контекст" }).click();
  await expect(panel).toHaveCount(0);
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href");
  const id = link?.split("/")[3];
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(raw).workspace.project?.operations).toHaveLength(2);
});

test("built E1 changed capture is rejected and source refresh preserves the typing buffer", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');
  await profile.click();
  await page.keyboard.press("End");
  await page.keyboard.type(" Added 😀");
  await profile.evaluate(field => {
    const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    if (!text) throw new Error("Profile text is missing");
    window.getSelection()?.setBaseAndExtent(text, 0, text, text.textContent?.length ?? 0);
    document.dispatchEvent(new Event("selectionchange"));
  });
  await page.getByRole("button", { name: "Показать исходник" }).click();
  const panel = page.getByRole("complementary", { name: "Исходный контекст" });
  await expect(panel.getByRole("status")).toContainText("Выделение устарело");
  await expect(panel.locator("blockquote")).toHaveCount(0);
  await expect(profile).toContainText("Added 😀");
});

test("built entry persists manual theme, follows system and fits a narrow keyboard layout", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByLabel("Тема", { exact: true }).selectOption("light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Тема", { exact: true }).selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Открыть пример" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Или вставьте текст")).not.toHaveValue("");
  await expect(page.getByRole("tab")).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(localStorage).filter(key => key !== "foldcv-theme"))).toEqual([]);
});

test("missing built next entry returns legacy HTTP 200 but fails the unique root smoke", async ({ page }) => {
  rmSync(resolve(runRoot, "dist/next.html"));
  const result = await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  expect(result?.status()).toBe(200);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме" })).toBeVisible();
});

test("chosen failed file disables inactive paste and explicit text recovery keeps project ID", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  const selected = page.waitForResponse(result => new URL(result.url()).pathname === "/v1/projects/input");
  await page.getByLabel("Файл резюме").setInputFiles({ name: "failed.pdf", mimeType: "application/pdf", buffer: Buffer.from("broken") });
  const selectedValue: unknown = await (await selected).json();
  const selectedWorkspace = response(selectedValue).workspace;
  await expect(page.getByText("Выбрано: failed.pdf", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Создать резюме" })).toBeDisabled();
  await expect(page.getByLabel("Или вставьте текст")).toHaveValue("");
  expect(selectedWorkspace.preDraft?.operations).toEqual([]);
  const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8");
  await page.getByLabel("Или вставьте текст").fill(raw);
  const created = page.waitForResponse(result => new URL(result.url()).pathname === `/v1/projects/${selectedWorkspace.projectId}/generations`);
  await page.getByRole("button", { name: "Создать резюме" }).click();
  const createdValue: unknown = await (await created).json();
  expect(response(createdValue).workspace.projectId).toBe(selectedWorkspace.projectId);
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
});
