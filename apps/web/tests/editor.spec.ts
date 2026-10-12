import { expect, test } from "@playwright/test";
import { acknowledgeVisibleWarnings } from "./export-review";

test.beforeEach(async ({ page }) => {
  await page.goto("/legacy.html");
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
});

test("draft navigation, apply, lock, undo and source text stay local", async ({ page }) => {
  let operations = 0;
  page.on("request", (request) => { if (request.url().includes("/v1/operations")) operations += 1; });
  const textarea = page.getByLabel("Текст блока");
  const original = await textarea.inputValue();
  await textarea.fill("Ручная правка профиля");
  await page.getByRole("button", { name: "Проект: Example One" }).click();
  await page.getByRole("button", { name: "О себе" }).click();
  await expect(textarea).toHaveValue("Ручная правка профиля");
  await expect(page.getByText("ввод не применён", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Применить правку" }).click();
  await expect(page.getByText("Правка закреплена")).toBeVisible();
  await expect(page.getByRole("button", { name: "Предложить новую формулировку" })).toHaveCount(0);
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await expect(textarea).toHaveValue(original);
  await page.getByRole("button", { name: "Показать источники" }).click();
  await expect(page.getByText("Built a team from zero to five", { exact: false })).toBeVisible();
  expect(operations).toBe(0);
});

test("empty text error, cancel and hidden block are visible", async ({ page }) => {
  const textarea = page.getByLabel("Текст блока");
  await textarea.fill(" ");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await expect(page.getByRole("alert")).toContainText("Введите текст блока");
  await page.getByRole("button", { name: "Отменить ввод", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Скрыть раздел" }).click();
  await expect(page.getByRole("button", { name: "О себе" })).toContainText("Скрыт");
  await expect(page.getByRole("tab", { name: "Превью" })).toBeVisible();
  await expect(page.getByText("PDF ещё не собран")).toBeVisible();
});

test("fact input error and correction invalidate review and mark preview stale", async ({ page }) => {
  await page.getByRole("button", { name: "Проект: Example One" }).click();
  await page.getByRole("button", { name: "Отметить блок проверенным" }).click();
  await page.getByRole("tab", { name: "Проверки" }).click();
  await expect(page.getByText("Выбранный блок отмечен проверенным")).toBeVisible();
  await page.getByLabel("Значение факта").fill("bad");
  await page.getByRole("button", { name: "Применить факт" }).click();
  await expect(page.getByRole("alert")).toContainText("Введите корректное значение факта");
  await page.getByLabel("Значение факта").fill("2500");
  await page.getByRole("button", { name: "Применить факт" }).click();
  await expect(page.getByText("Связанный факт изменён", { exact: false })).toBeVisible();
  await expect(page.getByText("Выбранный блок ещё не отмечен проверенным")).toBeVisible();
  await page.getByRole("tab", { name: "Превью" }).click();
  await expect(page.getByText("PDF ещё не собран")).toBeVisible();
});

test("keyboard tabs, 1280 desktop and narrow layout remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.getByLabel("Текст блока")).toBeInViewport();
  await page.getByRole("tab", { name: "Превью" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Источники" })).toHaveAttribute("data-state", "active");
  await page.setViewportSize({ width: 390, height: 800 });
  await expect(page.getByLabel("Текст блока")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Проверки" })).toBeVisible();
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);
});

test("reload clears candidate state while manual theme persists", async ({ page }) => {
  await page.getByLabel("Текст блока").fill("Несохранённый текст");
  await page.getByLabel("Тема").selectOption("dark");
  const beforeReload = await page.evaluate(async () => ({
    local: Object.keys(localStorage), session: Object.keys(sessionStorage),
    databases: (await indexedDB.databases()).map((entry) => entry.name), cache: await caches.keys(),
  }));
  expect(beforeReload).toEqual({ local: ["foldcv-theme"], session: [], databases: [], cache: [] });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Исходное резюме" })).toBeVisible();
  await expect(page.getByRole("button", { name: "2. Редактор" })).toBeDisabled();
  await expect(page.getByLabel("Тема")).toHaveValue("dark");
  const afterReload = await page.evaluate(async () => ({
    local: Object.keys(localStorage), session: Object.keys(sessionStorage),
    databases: (await indexedDB.databases()).map((entry) => entry.name), cache: await caches.keys(),
  }));
  expect(afterReload).toEqual(beforeReload);
});

test("export offers explicit PDF, DOCX and project archive", async ({ page }) => {
  let operations = 0;
  page.on("request", (request) => { if (request.url().includes("/v1/operations")) operations += 1; });
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  await expect(page.getByRole("button", { name: "Собрать и скачать PDF" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Собрать и скачать DOCX" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Скачать проект" })).toBeEnabled();
  expect(operations).toBe(0);
});

test("synthetic review links the stored source fragment without a working draft", async ({ page }) => {
  await page.getByRole("tab", { name: "Проверки" }).click();
  const metric = page.getByRole("tabpanel", { name: "Проверки" }).getByText(
    "Проверьте число, диапазон, предел, единицу и контекст метрики.").locator("..");
  await expect(metric).toContainText("Built a team from zero to five");
  await metric.getByRole("button", { name: "Исходник" }).click();
  await expect(page.getByRole("tabpanel", { name: "Источники" })).toContainText(
    "Built a team from zero to five and processed up to 2000 records per day.");
});

test("untrusted text remains inert and errors use theme color", async ({ page }) => {
  const markup = "<img src=x onerror=alert(1)>";
  await page.getByLabel("Текст блока").fill(markup);
  await page.getByRole("button", { name: "Применить правку" }).click();
  await expect(page.getByLabel("Текст блока")).toHaveValue(markup);
  expect(await page.locator("img").count()).toBe(0);
  await page.getByLabel("Текст блока").fill("");
  await page.getByRole("button", { name: "Применить правку" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Введите текст блока");
  const light = await alert.evaluate((element) => getComputedStyle(element).color);
  await page.getByLabel("Тема").selectOption("dark");
  const dark = await alert.evaluate((element) => getComputedStyle(element).color);
  expect(light).not.toEqual(dark);
});

test("open project requires confirmation before returning to import", async ({ page }) => {
  await page.getByLabel("Текст блока").fill("Принятая правка");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "1. Загрузка" }).click();
  await expect(page.getByRole("heading", { name: "Открыт вымышленный пример" })).toBeVisible();
  await page.getByRole("button", { name: "Закрыть пример и перейти к импорту" }).click();
  await expect(page.getByText("Несохранённые правки примера будут удалены.")).toBeVisible();
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByLabel("Текст блока")).toHaveValue("Принятая правка");
  await expect(page.getByRole("button", { name: "Отменить правку" })).toBeEnabled();
});

test("undo of accepted edit leaves a later pending draft", async ({ page }) => {
  const textarea = page.getByLabel("Текст блока");
  const original = await textarea.inputValue();
  await textarea.fill("Принятый текст");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await textarea.fill("Новый неприменённый текст");
  await page.getByRole("button", { name: "Отменить правку" }).click();
  await expect(textarea).toHaveValue("Новый неприменённый текст");
  await expect(page.getByText("PDF ещё не собран")).toBeVisible();
  await page.getByRole("button", { name: "Отменить ввод", exact: true }).click();
  await expect(textarea).toHaveValue(original);
});

test("equivalent metric notation keeps accepted review and normalizes field", async ({ page }) => {
  await page.getByRole("button", { name: "Проект: Example One" }).click();
  await page.getByRole("button", { name: "Отметить блок проверенным" }).click();
  await page.getByLabel("Значение факта").fill("02000");
  await page.getByRole("button", { name: "Применить факт" }).click();
  await expect(page.getByLabel("Значение факта")).toHaveValue("2000");
  await expect(page.getByRole("button", { name: "Снять отметку проверки" })).toBeEnabled();
  await expect(page.getByText("Связанный факт изменён", { exact: false })).toHaveCount(0);
});

test("technology fact uses a catalog choice instead of a generic value editor", async ({ page }) => {
  await page.getByRole("button", { name: "Фокус технологий" }).click();
  await expect(page.getByText("Python · внесено пользователем")).toBeVisible();
  await page.getByLabel("Технология из каталога").selectOption("docker");
  await page.getByRole("button", { name: "Применить технологию" }).click();
  await expect(page.getByText("docker · внесено пользователем")).toBeVisible();
  await expect(page.getByLabel("Значение факта")).toHaveCount(0);
  await expect(page.getByLabel("Текст блока")).toBeDisabled();
});
