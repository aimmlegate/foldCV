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
  await page.route("**/source-context", async route => {
    const value: unknown = route.request().postDataJSON();
    if (typeof value !== "object" || value === null || !("documentRevision" in value) || typeof value.documentRevision !== "number") throw new Error("Invalid context request");
    await route.continue({ postData: JSON.stringify({ ...value, documentRevision: value.documentRevision - 1 }) });
  });
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

test("built E1 continuous typing retains a session and real two-step block restore", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  const read = async () => { const value: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json(); return response(value).workspace; };
  const profile = page.locator('[data-field-content="profile/text"]'), original = await profile.innerText();
  await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "original"));
  await profile.click();await page.keyboard.press("End");
  await page.keyboard.type(" Long continuous user addition", { delay: 80 });
  await expect.poll(async () => (await read()).project?.document.profile.text.text).toContain("Long continuous user addition");
  expect((await read()).undoSlots["profile"]).toBeNull();
  expect((await read()).editSessions["profile"]?.baseline.record.kind).toBe("profile");
  expect((await read()).project?.operations).toHaveLength(2);
  await page.getByRole("button", { name: "Показать исходник" }).click();
  await expect(page.getByRole("complementary", { name: "Исходный контекст" }).getByRole("status")).toContainText("добавлен пользователем");
  await page.getByRole("button", { name: "Закрыть исходный контекст" }).click();
  await expect.poll(async () => (await read()).undoSlots["profile"]?.record.kind).toBe("profile");
  const first = await profile.innerText();
  await profile.click();await page.keyboard.press("End");await page.keyboard.type(" unfinished");
  await page.keyboard.press("Control+z");
  await expect(profile).toHaveText(first);
  expect((await read()).undoSlots["profile"]).not.toBeNull();
  await page.keyboard.press("Meta+z");
  await expect(profile).toHaveText(original);
  await expect.poll(async () => (await read()).undoSlots["profile"]).toBeNull();
  const revision = (await read()).documentRevision;
  await page.keyboard.press("Control+z");
  await expect(profile).toHaveText(original);
  await expect.poll(async () => (await read()).documentRevision).toBe(revision);
  await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "original");
});

test("built E1 lost acknowledgment retry applies once and keeps newer buffered text", async ({ page }) => {
  let interrupted = false;
  await page.route("**/mutations", async route => {
    if (!interrupted) { interrupted = true;await route.fetch();await route.abort("failed"); }
    else await route.continue();
  });
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();await page.keyboard.press("End");await page.keyboard.type(" First");
  await expect(page.getByRole("alert")).toContainText("Не удалось сохранить правки");
  await expect(profile).toContainText("First");
  await page.keyboard.type(" newer");
  await page.getByRole("button", { name: "Повторить сохранение" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("First newer");
  await expect(profile).toContainText("First newer");
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();const workspace = response(raw).workspace;
  expect(workspace.project?.operations).toHaveLength(2);expect(workspace.documentRevision).toBe(4);
  expect(workspace.editSessions["profile"]).toBeUndefined();
});

test("built E1 explicit rows periods and visibility survive editor projection changes", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByText("Разделы и строки", { exact: true }).click();
  await page.getByRole("button", { name: "Добавить работу", exact: true }).click();
  await expect(page.locator('[data-field-content$="/employer"]')).toHaveCount(3);
  await page.getByRole("button", { name: "Скрыть Работа 3", exact: true }).click();
  await expect(page.getByText("Работа 3 · скрыт из DOCX", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Показать Работа 3", exact: true }).click();
  await page.getByRole("button", { name: "Выше Работа 3", exact: true }).click();
  await expect(page.getByRole("button", { name: "Удалить Работа 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Удалить Работа 2", exact: true }).click();
  await expect(page.locator('[data-field-content$="/employer"]')).toHaveCount(2);
  await page.getByRole("button", { name: "Добавить образование", exact: true }).click();
  await expect(page.locator('[data-field-content$="/institution"]')).toHaveCount(2);
  await page.getByRole("button", { name: "Добавить язык", exact: true }).click();
  await expect(page.locator('[data-field-content^="language:"][data-field-content$="/name"]')).toHaveCount(3);
  await page.getByText("Периоды: Север", { exact: true }).click();
  const periods = page.locator('[data-period-job]').filter({ hasText: "Периоды: Север" });
  await periods.getByRole("button", { name: "Добавить период", exact: true }).click();
  await expect(periods.getByRole("checkbox")).toHaveCount(2);
  await periods.getByRole("button", { name: "Период выше" }).last().click();
  await periods.getByRole("button", { name: "Удалить период" }).first().click();
  await expect(periods.getByRole("checkbox")).toHaveCount(1);
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(periods.getByRole("checkbox")).toHaveCount(1);
  await expect(periods.getByRole("checkbox")).toBeChecked();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
});

test("built E1 delayed edit acknowledgment preserves newer typing and editor identity", async ({ page }) => {
  let release = () => {};const held = new Promise<void>(ready => { release = ready; });
  let admitted = () => {};const written = new Promise<void>(ready => { admitted = ready; });
  let first = true;
  await page.route("**/mutations", async route => {
    if (first) { first = false;const result = await route.fetch();admitted();await held;await route.fulfill({ response: result }); }
    else await route.continue();
  });
  try {
    await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
    await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
    await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
    const profile = page.locator('[data-field-content="profile/text"]');
    await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "original"));
    await profile.click();await page.keyboard.press("End");await page.keyboard.type(" First");
    await written;
    await page.keyboard.type(" newer");release();
    const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
    await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("First newer");
    await expect(profile).toContainText("First newer");
    await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "original");
    await expect(page.getByRole("alert")).toHaveCount(0);
  } finally { release(); }
});

test("built E1 active composition sends no partial mutation and retains completed IME text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();
  await profile.evaluate(field => {
    const root = document.querySelector('[contenteditable="true"]');const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    if (!root || !text) throw new Error("Profile text is missing");
    root.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
    text.textContent = `${text.textContent ?? ""}入力`;
    root.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertCompositionText", data: "入力", isComposing: true }));
  });
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(1200);
  const before: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(before).workspace.documentRevision).toBe(2);
  await profile.evaluate(field => {
    const root = field.closest('[contenteditable="true"]');
    root?.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "入力" }));
    root?.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: "入力" }));
  });
  await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("入力");
  await expect(profile).toContainText("入力");
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
